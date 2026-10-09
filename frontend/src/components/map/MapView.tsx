import { layers, namedFlavor } from "@protomaps/basemaps";
import type { GeoJSONSource, LayerSpecification, Map as MapLibreMap, Marker as MapLibreMarker, StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
// The worker as a URL, not a module: MapLibre derives its worker's address from
// where its own file sits, and Vite's dependency bundling moves that file, so
// the derived address 404s and the map draws nothing. The worker is one
// self-contained file, so Vite serves (and in a build, emits) it as it is.
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { corroborationLabel } from "../../lib/detectionVocabulary";
import { cn } from "../../lib/utils";
import type { AircraftTrack, InterferenceZone, RFSensor } from "../../types/operationalPicture";

// The map, and the only module in the app that touches a map library.
// spec: map-001, map-002, map-003, map-005, map-006.
//
// Everything else sees a component that takes receivers and aircraft and draws
// them, which is what lets every other test replace it wholesale and keeps the
// rest of the app ignorant of MapLibre. Its imports of `maplibre-gl` and
// `pmtiles` that execute anything are dynamic: with no basemap configured the
// library is never loaded, and a test proves it.
//
// Two basemaps, not of equal standing. The DEFAULT is Protomaps' light flavour
// over two archives served from this origin by `make basemap`: a Europe
// overview to zoom 6, drawn everywhere so the map never ends in grey, and the
// corpus box to zoom 10 drawn over it. SATELLITE is an optional orientation
// view, configured by an XYZ URL and its attribution, offered only when both
// are set and chosen only by the analyst. Nothing falls back to it, and when
// its tiles fail the screen says so rather than quietly drawing the default,
// which would make the two indistinguishable.
//
// Receivers and aircraft are HTML markers, not layers: each is a button with
// its state in its accessible name (map-003), opens one pop-up of payload
// fields (map-005), and survives a basemap switch, which wipes layers.
//
// An interference zone is both (map-006): a GeoJSON layer for the disc the
// claim was assessed over, re-added after every switch, and an HTML marker at
// its centre that carries the name, the label and the pop-up. The disc has no
// handlers of its own, so it never takes a click meant for a marker.

export interface SatelliteSource {
  tiles: string;
  attribution: string;
}

export interface BasemapConfig {
  defaultArchive: string | null;
  satellite: SatelliteSource | null;
}

type Env = Record<string, string | boolean | undefined>;

const setting = (env: Env, key: string): string | null => {
  const value = env[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
};

/** The basemap configuration from the frontend's environment. Empty means unset. */
export function readBasemapConfig(env: Env): BasemapConfig {
  const defaultArchive = setting(env, "VITE_BASEMAP_ARCHIVE");
  // A path on this server and nothing else: the default basemap is the one that
  // must work offline, so a URL to another host is refused rather than fetched.
  if (defaultArchive !== null && !/^\/[^/]/.test(defaultArchive)) {
    throw new Error(`VITE_BASEMAP_ARCHIVE must be a path on this server, such as /basemap/em-fusion.pmtiles, not ${defaultArchive}`);
  }
  const tiles = setting(env, "VITE_SATELLITE_TILES");
  const attribution = setting(env, "VITE_SATELLITE_ATTRIBUTION");
  return { defaultArchive, satellite: tiles && attribution ? { tiles, attribution } : null };
}

/** ODbL requires the OpenStreetMap credit; Protomaps built the tiles. Plain text: no URL in the style. */
const DEFAULT_ATTRIBUTION = "© OpenStreetMap contributors · Protomaps";

const FLAVOUR = namedFlavor("light");

/** Where the detailed box starts drawing over the overview, and the overview's labels stop. */
const DETAIL_FROM_ZOOM = 7;

const folderOf = (archive: string) => archive.slice(0, archive.lastIndexOf("/"));

/** The Europe overview `make basemap` puts beside the detailed archive. */
const overviewArchive = (archive: string) => `${folderOf(archive)}/europe-overview.pmtiles`;

/**
 * The self-hosted style. Glyphs and sprite sit beside the archives; a stock
 * Protomaps style points both at a CDN, and the map would still render.
 *
 * The overview draws at every zoom (overzoomed past its own 6), with its
 * labels only below 7 so they never collide with the box's. The box draws over
 * it from 7, without a background of its own: a second background would paint
 * over the overview wherever the box has no tiles, which is the grey edge again.
 */
export function buildDefaultStyle(archive: string): StyleSpecification {
  const folder = folderOf(archive);
  const overview = layers("overview", FLAVOUR, { lang: "en" }).map(
    (layer): LayerSpecification => ({
      ...layer,
      id: `overview-${layer.id}`,
      ...(layer.type === "symbol" ? { maxzoom: Math.min(layer.maxzoom ?? 24, DETAIL_FROM_ZOOM) } : {}),
    }),
  );
  const detail = layers("protomaps", FLAVOUR, { lang: "en" }).filter((layer) => layer.type !== "background");
  return {
    version: 8,
    glyphs: `${folder}/fonts/{fontstack}/{range}.pbf`,
    sprite: `${folder}/sprites/v4/light`,
    sources: {
      overview: { type: "vector", url: `pmtiles://${overviewArchive(archive)}`, attribution: DEFAULT_ATTRIBUTION },
      protomaps: { type: "vector", url: `pmtiles://${archive}`, attribution: DEFAULT_ATTRIBUTION, minzoom: DETAIL_FROM_ZOOM },
    },
    layers: [...overview, ...detail],
  };
}

/**
 * The style as this page hands it to MapLibre. MapLibre refuses a relative
 * sprite (it must be absolute), so the path is resolved against this page's
 * origin here: still this server, and the style itself keeps carrying paths.
 */
function onThisOrigin(style: StyleSpecification): StyleSpecification {
  return typeof style.sprite === "string" ? { ...style, sprite: new URL(style.sprite, window.location.origin).href } : style;
}

export function buildSatelliteStyle(satellite: SatelliteSource): StyleSpecification {
  return {
    version: 8,
    sources: {
      satellite: { type: "raster", tiles: [satellite.tiles], tileSize: 256, attribution: satellite.attribution },
    },
    layers: [{ id: "satellite", type: "raster", source: "satellite" }],
  };
}

// ------------------------------------------------------------- the zones

/** The mean Earth radius (IUGG), in km. */
const EARTH_RADIUS_KM = 6371.0088;

/**
 * The disc a zone was assessed over, as a closed ring of [lon, lat] vertices
 * (map-006 (1)). Each vertex is the point `radiusKm` along the great circle
 * from the centre on its bearing, so the ring is the geodesic circle and not
 * a circle in degrees, which at 50°N would be two-thirds as wide as it is tall.
 */
export function zoneOutline(centre: { lat: number; lon: number }, radiusKm: number, steps = 64): [number, number][] {
  const rad = Math.PI / 180;
  const lat1 = centre.lat * rad;
  const lon1 = centre.lon * rad;
  const angular = radiusKm / EARTH_RADIUS_KM;
  const ring: [number, number][] = [];
  for (let step = 0; step < steps; step++) {
    const bearing = (2 * Math.PI * step) / steps;
    const lat2 = Math.asin(Math.sin(lat1) * Math.cos(angular) + Math.cos(lat1) * Math.sin(angular) * Math.cos(bearing));
    const lon2 = lon1 + Math.atan2(Math.sin(bearing) * Math.sin(angular) * Math.cos(lat1), Math.cos(angular) - Math.sin(lat1) * Math.sin(lat2));
    ring.push([lon2 / rad, lat2 / rad]);
  }
  ring.push(ring[0]);
  return ring;
}

const ZONE_SOURCE = "zones";

/** Only zones with a recorded radius have a disc (map-006 (4)). */
const zoneDiscs = (zones: InterferenceZone[]) => ({
  type: "FeatureCollection" as const,
  features: zones.flatMap((zone) =>
    zone.radiusKm === null
      ? []
      : [
          {
            type: "Feature" as const,
            properties: { id: zone.id },
            geometry: { type: "Polygon" as const, coordinates: [zoneOutline(zone.centre, zone.radiusKm)] },
          },
        ],
  ),
});

/**
 * DESIGN.md's error-container red: the one token family no marker uses, so the
 * disc never reads as part of the orange anomalous markers inside it, and far
 * darker than that orange, so the two stay apart for red-green colour blindness.
 */
const ZONE_COLOUR = "#93000a";

/** Faint enough that the basemap and the aircraft inside stay readable; dashed because it is an assessed area, not an edge. */
const ZONE_LAYERS: LayerSpecification[] = [
  { id: "zones-fill", type: "fill", source: ZONE_SOURCE, paint: { "fill-color": ZONE_COLOUR, "fill-opacity": 0.08 } },
  {
    id: "zones-line",
    type: "line",
    source: ZONE_SOURCE,
    paint: { "line-color": ZONE_COLOUR, "line-width": 1.5, "line-dasharray": [3, 2] },
  },
];

// ------------------------------------------------------------ the entities

type Kind = "receiver" | "aircraft" | "zone";

/** The states `api-007`'s anomalous view admits: one definition of anomalous. */
const ANOMALOUS = new Set(["fault", "deviating", "interrupted"]);

/**
 * How a marker is drawn for its state (map-003 (1)). DESIGN.md tokens, with a
 * white outline so they read on the light basemap. Anomalous is one orange
 * for both kinds; nominal is each kind's own colour; not examined is grey and
 * hollow, and never the nominal look.
 */
export function markerLook(kind: Exclude<Kind, "zone">, state: string): { fill: string; stroke: string } {
  if (ANOMALOUS.has(state)) return { fill: "#df7412", stroke: "#ffffff" };
  if (state === "nominal") return { fill: kind === "aircraft" ? "#005ac2" : "#00424e", stroke: "#ffffff" };
  return { fill: "none", stroke: "#424754" };
}

/** A state as the map names it: `unknown` is what it means, not the word. */
const stateWord = (state: string) => (state === "unknown" ? "not examined" : state);

/** The exception panel's wording for an altitude. */
const altitude = (feet: number | null): string => (feet === null ? "not reported" : `${feet.toLocaleString("en-GB")} ft`);

const position = (lat: number, lon: number) =>
  `${Math.abs(lat).toFixed(4)}° ${lat >= 0 ? "N" : "S"}, ${Math.abs(lon).toFixed(4)}° ${lon >= 0 ? "E" : "W"}`;

interface Entity {
  key: string;
  kind: Kind;
  name: string;
  state: string;
  lat: number;
  lon: number;
  /** The pop-up's rows: payload fields only (map-005). */
  fields: [string, string][];
  /** Lower is more important when two labels collide (map-005 (2)). */
  rank: number;
  sensor?: RFSensor;
  track?: AircraftTrack;
  zone?: InterferenceZone;
}

/** "RF-01", "RF-01 and RF-02", "RF-01, RF-02 and RF-03". */
const listed = (names: string[]) => (names.length < 2 ? names.join("") : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`);

/** A zone's window in simulated time, in UTC: the payload's instants, reformatted. */
function zoneWindow(zone: InterferenceZone): string {
  const [from, to] = [zone.startedAt, zone.endedAt].map((iso) => new Date(iso).toISOString());
  const day = from.slice(0, 10);
  const end = to.slice(0, 10) === day ? to.slice(11, 19) : `${to.slice(0, 10)} ${to.slice(11, 19)}`;
  return `${day} ${from.slice(11, 19)} – ${end} UTC`;
}

function entitiesOf(sensors: RFSensor[], tracks: AircraftTrack[], zones: InterferenceZone[]): Entity[] {
  return [
    ...zones.map(
      (zone): Entity => ({
        key: `zone:${zone.id}`,
        kind: "zone",
        name: `Interference zone over ${listed(zone.receivers)}, ${zone.confidence} confidence`,
        state: "zone",
        lat: zone.centre.lat,
        lon: zone.centre.lon,
        fields: [
          ["Receivers", zone.receivers.join(", ")],
          ["Window", zoneWindow(zone)],
          ["Confidence", zone.confidence],
          ["Aircraft", corroborationLabel(zone.corroboration)],
          ["Centre", position(zone.centre.lat, zone.centre.lon)],
        ],
        // Above every other label: the conclusion is what the map is for.
        rank: -1,
        zone,
      }),
    ),
    ...sensors.map(
      (sensor): Entity => ({
        key: `receiver:${sensor.id}`,
        kind: "receiver",
        name: `Receiver ${sensor.id} (${sensor.stationName}), ${stateWord(sensor.health)}`,
        state: sensor.health,
        lat: sensor.lat,
        lon: sensor.lon,
        fields: [
          ["Receiver", sensor.id],
          ["Station", sensor.stationName],
          ["Band", sensor.signalId],
          ["State", stateWord(sensor.health)],
          ["Position", position(sensor.lat, sensor.lon)],
        ],
        rank: ANOMALOUS.has(sensor.health) ? 0 : 1,
        sensor,
      }),
    ),
    ...tracks.map(
      (track): Entity => ({
        key: `aircraft:${track.id}`,
        kind: "aircraft",
        name: `Aircraft ${track.name}, ${stateWord(track.state)}`,
        state: track.state,
        lat: track.lat,
        lon: track.lon,
        fields: [
          ["Aircraft", track.name],
          ["Altitude", altitude(track.altitudeFt)],
          ["State", stateWord(track.state)],
          ["Position", position(track.lat, track.lon)],
        ],
        rank: ANOMALOUS.has(track.state) ? 2 : 3,
        track,
      }),
    ),
  ];
}

/** Every aircraft is labelled from this zoom; below it, only interrupted ones. */
const ALL_AIRCRAFT_LABELS_FROM_ZOOM = 9;

function labelOf(entity: Entity, zoom: number): string | null {
  if (entity.zone) return `Possible interference · ${entity.zone.confidence}`;
  if (entity.sensor) return entity.sensor.stationName;
  const track = entity.track;
  if (!track || (!ANOMALOUS.has(track.state) && zoom < ALL_AIRCRAFT_LABELS_FROM_ZOOM)) return null;
  return track.altitudeFt === null ? track.name : `${track.name} · ${altitude(track.altitudeFt)}`;
}

export interface LabelCandidate {
  id: string;
  rank: number;
  x: number;
  y: number;
  text: string;
}

/**
 * Which labels to show, so none overlaps another (map-005 (2)). Greedy by rank:
 * a label is kept unless it would overlap one already kept, so where two collide
 * the more important one survives whatever order they arrive in. The box is an
 * estimate from the text's length (11 px monospace), centred under the icon.
 *
 * A label also gives way to the icon of any entity at least as important as its
 * own (`icons`), so a cluster's labels never cover the icons that matter; a less
 * important icon does not hide it, so an anomalous receiver's name always shows.
 */
export function placeLabels(candidates: LabelCandidate[], icons: Omit<LabelCandidate, "text">[] = []): Set<string> {
  type Box = { left: number; top: number; right: number; bottom: number };
  const overlaps = (a: Box, b: Box) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
  const iconBox = (icon: Omit<LabelCandidate, "text">): Box => ({ left: icon.x - 12, right: icon.x + 12, top: icon.y - 12, bottom: icon.y + 12 });
  const kept: Box[] = [];
  const shown = new Set<string>();
  for (const candidate of [...candidates].sort((a, b) => a.rank - b.rank)) {
    const width = candidate.text.length * 6.6 + 10;
    const box = { left: candidate.x - width / 2, right: candidate.x + width / 2, top: candidate.y + 14, bottom: candidate.y + 32 };
    if (kept.some((other) => overlaps(box, other))) continue;
    if (icons.some((icon) => icon.id !== candidate.id && icon.rank <= candidate.rank && overlaps(box, iconBox(icon)))) continue;
    kept.push(box);
    shown.add(candidate.id);
  }
  return shown;
}

function ZoneIcon() {
  return (
    <svg
      width="24"
      height="24"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <circle
        cx="12"
        cy="12"
        r="9.5"
        fill="#ffffff"
        stroke={ZONE_COLOUR}
        strokeWidth="2"
        strokeDasharray="3 2"
      />
      <circle
        cx="12"
        cy="12"
        r="4"
        fill={ZONE_COLOUR}
        stroke="#ffffff"
        strokeWidth="1.5"
      />
    </svg>
  );
}

function Icon({ kind, state }: { kind: Kind; state: string }) {
  if (kind === "zone") return <ZoneIcon />;
  const look = markerLook(kind, state);
  const ink = look.fill === "none" ? look.stroke : look.fill;
  return (
    <svg
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill={look.fill}
      stroke={look.stroke}
      strokeWidth="1.5"
      aria-hidden="true"
    >
      {kind === "aircraft" ? (
        // Fixed orientation: the payload carries no heading, and this does not imply one.
        <path
          d="M12 1.5 13.6 9 22.5 13.2v2.1l-8.9-2.6-.5 6.2 3 2.1v1.5l-4.1-1.1-4.1 1.1V21l3-2.1-.5-6.2-8.9 2.6v-2.1L10.4 9z"
          strokeLinejoin="round"
        />
      ) : (
        <>
          <path
            d="M12 9.5 17 22.5h-2.4L12 15.6 9.4 22.5H7z"
            strokeLinejoin="round"
          />
          <circle
            cx="12"
            cy="7.5"
            r="2.4"
          />
          <path
            d="M7.4 3.2a6.5 6.5 0 0 0 0 8.6M16.6 3.2a6.5 6.5 0 0 1 0 8.6"
            fill="none"
            stroke={ink}
            strokeWidth="1.8"
            strokeLinecap="round"
          />
        </>
      )}
    </svg>
  );
}

// ------------------------------------------------------------ the pop-up

/** Clearance between the pop-up and its marker's centre: half the 24 px icon and a margin. */
const POPUP_GAP = 18;

/** How much of a moved pop-up must stay inside the map, so it can always be dragged back. */
const POPUP_KEEP = 40;

/** One arrow-key press on the move handle (map-005 (3)). */
const POPUP_STEP = 16;

interface Size {
  width: number;
  height: number;
}

interface Point {
  x: number;
  y: number;
}

const clamp = (value: number, low: number, high: number) => Math.min(Math.max(value, low), Math.max(low, high));

/**
 * Where a pop-up opens: its top-left corner in the map's pixels (map-005 (3)).
 * Above the marker when it fits, below it when it does not, then beside it --
 * right, then left -- so a tall pop-up on a short map does not cover the marker
 * it describes; pulled in from the edges either way, so it never opens clipped
 * when the map has room for it.
 */
function fittedCorner(anchor: Point, popup: Size, map: Size): Point {
  const x = clamp(anchor.x - popup.width / 2, 0, map.width - popup.width);
  const above = anchor.y - POPUP_GAP - popup.height;
  if (above >= 0) return { x, y: above };
  const below = anchor.y + POPUP_GAP;
  if (below + popup.height <= map.height) return { x, y: below };
  const y = clamp(anchor.y - popup.height / 2, 0, map.height - popup.height);
  const right = anchor.x + POPUP_GAP;
  if (right + popup.width <= map.width) return { x: right, y };
  const left = anchor.x - POPUP_GAP - popup.width;
  return { x: left >= 0 ? left : x, y };
}

/** A moved pop-up's corner: its offset from the marker, kept far enough inside the map to grab again. */
function movedCorner(anchor: Point, offset: Point, popup: Size, map: Size): Point {
  return {
    x: clamp(anchor.x + offset.x, POPUP_KEEP - popup.width, map.width - POPUP_KEEP),
    y: clamp(anchor.y + offset.y, 0, map.height - POPUP_KEEP),
  };
}

const ARROWS: Record<string, Point> = {
  ArrowLeft: { x: -POPUP_STEP, y: 0 },
  ArrowRight: { x: POPUP_STEP, y: 0 },
  ArrowUp: { x: 0, y: -POPUP_STEP },
  ArrowDown: { x: 0, y: POPUP_STEP },
};

// ----------------------------------------------------------------- the view

/** Reads the archive's header: a missing file is caught before a map is made. */
async function readArchiveHeader(archive: string): Promise<void> {
  const { PMTiles } = await import("pmtiles");
  await new PMTiles(archive).getHeader();
}

let pmtilesRegistered = false;

/** The corpus box (implementation.md): 3–11°E, 49–54°N. Where the map opens. */
const CORPUS_BOUNDS: [[number, number], [number, number]] = [
  [3, 49],
  [11, 54],
];

/** The Europe overview's box (map-001 (11)): the camera stays inside it. */
const OVERVIEW_BOUNDS: [[number, number], [number, number]] = [
  [-11, 35],
  [30, 61],
];

type Status = "unconfigured" | "loading" | "unreadable" | "failed" | "map";
type Basemap = "default" | "satellite";
type MapLibre = typeof import("maplibre-gl");

function configFromEnv(): BasemapConfig | Error {
  try {
    return readBasemapConfig(import.meta.env);
  } catch (error) {
    return error instanceof Error ? error : new Error(String(error));
  }
}

const count = (n: number, noun: string) => `${n} ${noun}${n === 1 ? "" : "s"}`;

const sameSet = (a: Set<string>, b: Set<string>) => a.size === b.size && [...a].every((item) => b.has(item));

export interface MapViewProps {
  sensors: RFSensor[];
  tracks: AircraftTrack[];
  /** The interference claims the payload placed (map-006). */
  zones?: InterferenceZone[];
  // The playback cursor in simulated time, or null at the end of the hour
  // (op-008). Handed down now and read by map-004.
  cursor?: string | null;
  /** Defaults to the frontend's environment. */
  config?: BasemapConfig | Error;
  /** Defaults to reading the PMTiles header. Rejects when the archive cannot be read. */
  readArchive?: (archive: string) => Promise<void>;
}

export function MapView({ sensors, tracks, zones = [], config = configFromEnv(), readArchive = readArchiveHeader }: MapViewProps) {
  const settings = config instanceof Error ? null : config;
  const archive = settings?.defaultArchive ?? null;
  const satellite = settings?.satellite ?? null;

  const container = useRef<HTMLDivElement>(null);
  const sectionRef = useRef<HTMLElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const libRef = useRef<MapLibre | null>(null);
  const basemapRef = useRef<Basemap>("default");
  const markersRef = useRef(new Map<string, { marker: MapLibreMarker; element: HTMLElement }>());
  const entities = entitiesOf(sensors, tracks, zones);
  const entitiesRef = useRef(entities);
  entitiesRef.current = entities;
  const zonesRef = useRef(zones);
  zonesRef.current = zones;

  const [status, setStatus] = useState<Status>(archive ? "loading" : "unconfigured");
  const [basemap, setBasemap] = useState<Basemap>("default");
  const [satelliteFailing, setSatelliteFailing] = useState(false);
  const [hosts, setHosts] = useState<Map<string, HTMLElement>>(new Map());
  const [labelled, setLabelled] = useState<Map<string, string>>(new Map());
  const [selected, setSelected] = useState<string | null>(null);
  const [, setMoved] = useState(0);
  // The pop-up's measured size and the map's, read after layout; and, once the
  // analyst has moved it, its offset from the marker for the entity it was moved for.
  const [popupSize, setPopupSize] = useState<Size | null>(null);
  const [mapSize, setMapSize] = useState<Size>({ width: 0, height: 0 });
  const [dragged, setDragged] = useState<{ key: string; offset: Point } | null>(null);
  const selectedRef = useRef(selected);
  selectedRef.current = selected;

  /** Which labels to show at the camera's current zoom and position. */
  const relabel = () => {
    const map = mapRef.current;
    if (!map) return;
    const zoom = map.getZoom();
    const candidates: LabelCandidate[] = [];
    const icons: Omit<LabelCandidate, "text">[] = [];
    const texts = new Map<string, string>();
    for (const entity of entitiesRef.current) {
      const { x, y } = map.project([entity.lon, entity.lat]);
      icons.push({ id: entity.key, rank: entity.rank, x, y });
      const text = labelOf(entity, zoom);
      if (text === null) continue;
      candidates.push({ id: entity.key, rank: entity.rank, x, y, text });
      texts.set(entity.key, text);
    }
    const shown = placeLabels(candidates, icons);
    const next = new Map([...texts].filter(([key]) => shown.has(key)));
    setLabelled((current) =>
      sameSet(new Set(current.keys()), new Set(next.keys())) && [...next].every(([key, text]) => current.get(key) === text) ? current : next,
    );
  };
  const relabelRef = useRef(relabel);
  relabelRef.current = relabel;

  /**
   * The discs, into the current style. A style switch wipes sources and
   * layers, so this runs on every style load as well as when zones change.
   */
  const drawZones = () => {
    const map = mapRef.current;
    if (!map) return;
    const data = zoneDiscs(zonesRef.current);
    const source = map.getSource(ZONE_SOURCE) as GeoJSONSource | undefined;
    if (source) {
      source.setData(data);
      return;
    }
    map.addSource(ZONE_SOURCE, { type: "geojson", data });
    for (const layer of ZONE_LAYERS) map.addLayer(layer);
  };

  // biome-ignore lint/correctness/useExhaustiveDependencies: readArchive is a seam for tests; the map is built once per archive.
  useEffect(() => {
    if (!archive) return;
    let cancelled = false;
    const markers = markersRef.current;

    (async () => {
      try {
        await Promise.all([readArchive(archive), readArchive(overviewArchive(archive))]);
      } catch {
        if (!cancelled) setStatus("unreadable");
        return;
      }
      const maplibre = await import("maplibre-gl");
      if (cancelled || !container.current) return;
      maplibre.setWorkerUrl(maplibreWorkerUrl);
      if (!pmtilesRegistered) {
        const { Protocol } = await import("pmtiles");
        maplibre.addProtocol("pmtiles", new Protocol().tile);
        pmtilesRegistered = true;
      }
      let map: MapLibreMap;
      try {
        map = new maplibre.Map({
          container: container.current,
          style: onThisOrigin(buildDefaultStyle(archive)),
          bounds: CORPUS_BOUNDS,
          maxBounds: OVERVIEW_BOUNDS,
          attributionControl: { compact: false },
        });
      } catch {
        setStatus("failed");
        return;
      }
      mapRef.current = map;
      libRef.current = maplibre;
      map.addControl(new maplibre.NavigationControl({ showCompass: false }));
      map.on("moveend", () => relabelRef.current());
      map.on("load", drawZones);
      map.on("style.load", drawZones);
      // The pop-up is placed in screen space, so it follows the camera.
      map.on("move", () => {
        if (selectedRef.current) setMoved((n) => n + 1);
      });
      map.on("click", (event) => {
        // A click on a marker reaches the map too; it is the marker's to handle.
        const target = (event as { originalEvent?: { target?: unknown } }).originalEvent?.target;
        if (target instanceof Element && target.closest("[data-map-marker]")) return;
        setSelected(null);
      });
      map.on("error", (event) => {
        // A failed tile carries the id of the source it was for.
        if ((event as { sourceId?: string }).sourceId === "satellite") {
          if (basemapRef.current === "satellite") setSatelliteFailing(true);
          return;
        }
        // Listening for errors stops MapLibre logging them, so anything else is
        // passed on rather than swallowed: a broken sprite was silent this way.
        console.error(event.error);
      });
      setStatus("map");
    })();

    return () => {
      cancelled = true;
      for (const { marker } of markers.values()) marker.remove();
      markers.clear();
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, [archive]);

  // The markers follow the payload: added, moved and removed as rows arrive
  // and leave (map-001 (12)). Each is an empty element MapLibre positions;
  // React renders the button into it through a portal.
  useEffect(() => {
    const map = mapRef.current;
    const maplibre = libRef.current;
    if (status !== "map" || !map || !maplibre) return;
    const current = markersRef.current;
    const keys = new Set(entities.map((entity) => entity.key));
    let changed = false;
    for (const [key, { marker }] of current) {
      if (keys.has(key)) continue;
      marker.remove();
      current.delete(key);
      changed = true;
    }
    for (const entity of entities) {
      const existing = current.get(entity.key);
      if (existing) {
        existing.marker.setLngLat([entity.lon, entity.lat]);
        continue;
      }
      const element = document.createElement("div");
      element.dataset.mapMarker = entity.kind;
      // The more important entity draws on top: an anomalous receiver is never
      // buried under a cluster of aircraft.
      element.style.zIndex = String(4 - entity.rank);
      const marker = new maplibre.Marker({ element, anchor: "center" }).setLngLat([entity.lon, entity.lat]).addTo(map);
      current.set(entity.key, { marker, element });
      changed = true;
    }
    if (changed) setHosts(new Map([...current].map(([key, { element }]) => [key, element])));
    relabelRef.current();
  });

  // A changed set of zones redraws the discs; before the style has loaded there
  // is no source yet, and the load handler draws them.
  const zoneKey = zones.map((zone) => `${zone.id}|${zone.radiusKm}|${zone.centre.lat}|${zone.centre.lon}`).join(";");
  // biome-ignore lint/correctness/useExhaustiveDependencies: zoneKey stands for the zones' drawn content.
  useEffect(() => {
    if (status !== "map" || !mapRef.current?.getSource(ZONE_SOURCE)) return;
    drawZones();
  }, [zoneKey, status]);

  // A pop-up for an entity the payload no longer carries closes (map-005).
  const popup = entities.find((entity) => entity.key === selected) ?? null;
  useEffect(() => {
    if (selected && !popup) setSelected(null);
  }, [selected, popup]);

  // Any change of pop-up -- closed, reopened or replaced -- opens in its fitted place.
  // biome-ignore lint/correctness/useExhaustiveDependencies: the reset is keyed on the selection itself.
  useEffect(() => setDragged(null), [selected]);

  // Sizes are read after layout and stored only when they change, so this settles in one pass.
  useLayoutEffect(() => {
    const measure = (element: Element | null): Size | null => {
      if (!element) return null;
      const { width, height } = element.getBoundingClientRect();
      return { width, height };
    };
    const same = (a: Size | null, b: Size | null) => a?.width === b?.width && a?.height === b?.height;
    const map = measure(sectionRef.current);
    if (map && !same(map, mapSize)) setMapSize(map);
    const popup = measure(popupRef.current);
    if (popup && !same(popup, popupSize)) setPopupSize(popup);
  });

  useEffect(() => {
    if (!selected) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSelected(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [selected]);

  const choose = (next: Basemap) => {
    const map = mapRef.current;
    if (!map || !archive || next === basemap) return;
    if (next === "satellite" && !satellite) return;
    basemapRef.current = next;
    setBasemap(next);
    setSatelliteFailing(false);
    // Rebuilt rather than diffed: a successful diff fires no style.load and drops
    // the zone source, so the discs would vanish with nothing to redraw them.
    map.setStyle(next === "satellite" && satellite ? buildSatelliteStyle(satellite) : onThisOrigin(buildDefaultStyle(archive)), { diff: false });
  };

  const counts = `${count(sensors.length, "receiver")} · ${tracks.length} aircraft`;
  const message =
    config instanceof Error
      ? `No basemap is configured: ${config.message}.`
      : status === "unconfigured"
        ? "No basemap is configured, so there is no map to draw."
        : status === "failed"
          ? "This browser could not start the map. It may not support WebGL."
          : null;
  const anchor = popup && mapRef.current ? mapRef.current.project([popup.lon, popup.lat]) : null;
  const size = popupSize ?? { width: 0, height: 0 };
  const offset = dragged && dragged.key === selected ? dragged.offset : null;
  const corner = anchor ? (offset ? movedCorner(anchor, offset, size, mapSize) : fittedCorner(anchor, size, mapSize)) : null;

  /** Moves the open pop-up by a distance, starting from wherever it is drawn now. */
  const moveBy = (from: Point, delta: Point) => {
    if (!anchor || !selected) return;
    setDragged({ key: selected, offset: { x: from.x - anchor.x + delta.x, y: from.y - anchor.y + delta.y } });
  };

  const startDrag = (event: React.PointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0 || !corner) return;
    const start = { x: event.clientX, y: event.clientY };
    const from = corner;
    // Capture keeps the drag when the pointer outruns the handle. It throws for a
    // pointer the browser does not consider active, which must not cancel the drag.
    try {
      event.currentTarget.setPointerCapture?.(event.pointerId);
    } catch {}
    const onMove = (move: PointerEvent) => moveBy(from, { x: move.clientX - start.x, y: move.clientY - start.y });
    const onUp = (up: PointerEvent) => {
      onMove(up);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  return (
    <section
      ref={sectionRef}
      aria-label="Map"
      className="relative h-full min-h-[320px] w-full overflow-hidden border border-[#424754] bg-black"
    >
      {/* MapLibre sets position: relative on its container, so the container fills a positioned wrapper. */}
      <div className="absolute inset-0">
        <div
          ref={container}
          className="h-full w-full"
        />
      </div>

      {status === "map" &&
        entities.map((entity) => {
          const host = hosts.get(entity.key);
          if (!host) return null;
          const label = labelled.get(entity.key);
          return createPortal(
            <button
              type="button"
              aria-label={entity.name}
              onClick={(event) => {
                event.stopPropagation();
                setSelected(entity.key);
              }}
              className="relative block h-6 w-6 cursor-pointer"
            >
              <Icon
                kind={entity.kind}
                state={entity.state}
              />
              {label && (
                <span className="pointer-events-none absolute left-1/2 top-[26px] -translate-x-1/2 whitespace-nowrap border border-[#424754] bg-[#10131a]/90 px-1 font-mono text-[11px] leading-4 text-[#e1e2ec]">
                  {label}
                </span>
              )}
            </button>,
            host,
            entity.key,
          );
        })}

      {popup && corner && (
        <div
          ref={popupRef}
          role="dialog"
          aria-label={
            popup.kind === "aircraft" ? `Aircraft ${popup.track?.name}` : popup.kind === "zone" ? "Possible interference" : `Receiver ${popup.sensor?.id}`
          }
          className="absolute z-10 w-72 border border-[#424754] bg-[#10131a] p-3 text-xs text-[#e1e2ec] shadow-lg"
          // Hidden for the one render before its size is known, so it never flashes in the wrong place.
          style={{ left: corner.x, top: corner.y, visibility: popupSize ? "visible" : "hidden" }}
        >
          <div className="mb-2 flex items-center justify-between gap-2">
            {/* The header is the move handle: dragged with a pointer, or nudged with the arrow keys. */}
            <button
              type="button"
              aria-label="Move pop-up (drag, or use the arrow keys)"
              onPointerDown={startDrag}
              onKeyDown={(event) => {
                const delta = ARROWS[event.key];
                if (!delta || !corner) return;
                event.preventDefault();
                moveBy(corner, delta);
              }}
              className="flex-1 cursor-move touch-none select-none text-left font-mono uppercase tracking-[0.05em] text-[#8c909f]"
            >
              {popup.kind === "zone" ? "Possible interference" : popup.kind}
            </button>
            <button
              type="button"
              aria-label="Close"
              onClick={() => setSelected(null)}
              className="px-1 text-[#8c909f] hover:text-[#e1e2ec]"
            >
              ×
            </button>
          </div>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
            {popup.fields.map(([term, value]) => (
              <div
                key={term}
                className="contents"
              >
                <dt className="text-[#8c909f]">{term}</dt>
                <dd className={cn("font-mono", term === "State" && ANOMALOUS.has(popup.state) && "text-[#ffb786]")}>{value}</dd>
              </div>
            ))}
          </dl>
          {popup.zone && (
            <p className="mt-2 border-t border-[#424754] pt-2 text-[#c2c6d6]">
              {popup.zone.radiusKm === null
                ? "No assessed radius was recorded with this conclusion, so no circle is drawn. The system does not estimate how far interference reaches."
                : `The circle is the ${popup.zone.radiusKm} km area the rule assessed, not a measured extent of the interference.`}
            </p>
          )}
        </div>
      )}

      {(message || status === "unreadable") && (
        <div className="absolute inset-0 flex flex-col justify-center gap-2 p-6">
          <p className="font-mono text-xs uppercase tracking-[0.05em] text-[#8c909f]">Map</p>
          {status === "unreadable" ? (
            <p className="text-sm text-[#e1e2ec]">
              The basemap at {archive} could not be read. Download it with <code className="font-mono">make basemap</code>.
            </p>
          ) : (
            <p className="text-sm text-[#e1e2ec]">{message}</p>
          )}
          <p className="font-mono text-xs text-[#8c909f]">{counts}</p>
        </div>
      )}

      {status === "map" && satellite && (
        <div className="absolute left-2 top-2 flex border border-[#424754] bg-[#10131a] font-mono text-xs uppercase">
          {(["default", "satellite"] as const).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={basemap === option}
              onClick={() => choose(option)}
              className={cn("px-3 py-1.5 text-[#8c909f]", basemap === option && "bg-[#424754] text-[#e1e2ec]")}
            >
              {option === "default" ? "Map" : "Satellite"}
            </button>
          ))}
        </div>
      )}

      {satelliteFailing && basemap === "satellite" && (
        <p
          role="status"
          className="absolute inset-x-2 bottom-8 border border-[#ffb786] bg-[#10131a] p-2 text-xs text-[#ffb786]"
        >
          Satellite tiles are failing to load. Nothing is drawn in their place; switch back to Map for the offline basemap.
        </p>
      )}
    </section>
  );
}
