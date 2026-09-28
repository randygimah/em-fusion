# Hypothesis scoring pack

20 evidence packs. Under each one are two short explanations, labelled A and B. They were produced by two different systems. You are not told which is which, and **the labels are reshuffled on every pack** -- A here has nothing to do with A on the next one.

Each pack is laid out the same way: what the detection rules concluded, the findings behind that conclusion, and what the rules could not determine. Read the pack first, then both explanations, then score each one **on its own terms** in the scoring workbook.

Findings are grouped by the rule that produced them, and every finding is still listed individually under its group. The grouping is there to save you re-reading near-identical lines; it is not a summary, and nothing has been left out.

Two explanations under one pack may occasionally be identical or nearly so. That is expected rather than a fault in the pack.

---

## Terms used in these packs

Definitions, not interpretations: each entry says what the word refers to, and deliberately not what it would mean if you saw it. Judging that is the job.

| Term | What it refers to |
|---|---|
| `FUSION-SPATIAL` | The rule that reports when more than one receiver deviated in the same area and the same window. |
| `RF-NOISE` | The rule that compares each radio reading against what that receiver normally reads on that channel. |
| `SENSOR-FAULT` | The rule that compares one receiver against the receivers near it. |
| `TRACK-GAP` | The rule that looks for aircraft whose position reports stop arriving. |
| `possible_interference_zone` | The conclusion that more than one receiver deviated at the same time in the same area. |
| `possible_sensor_fault` | The conclusion that one receiver deviated while the neighbours that could be measured stayed within their normal range. |
| `channel_adjacency` | How many of a receiver's channels the deviation covered, out of the total it watches. |
| `neighbour_nominal` | A receiver near the one under examination that was measured and stayed within its normal range. |
| `power_dbm` | Received signal power, in decibels relative to one milliwatt. |
| `rf_noise_deviation` | One run of consecutive readings on one receiver and one channel that sat far enough from that cell's normal to be recorded as an event. |
| `track_continuity_gap` | One aircraft's position reports stopping for longer than the gap the rule allows. |
| `track_rate_excess` | How often aircraft dropped out inside the window, set against how often they dropped out in the same area outside it. |
| `baseline` | The average and spread of what one receiver reads on one channel, worked out from quiet periods only. Every receiver and channel has its own; they are never pooled. |
| `channel` | One slice of the radio spectrum. Each receiver watches several, numbered from 0. |
| `corroborate` | To look for agreement from the other half of the picture -- the aircraft side for a radio finding, and the reverse. Recorded as one of three values: corroborated, measured and not corroborated, or not measurable. |
| `dB` | Decibel, the unit these readings use. It is a ratio on a logarithmic scale: 3 dB is about double, 10 dB is ten times, 20 dB is a hundred times. |
| `disc` | A circular area of the stated radius, centred on the event, used to decide which aircraft count as near it. |
| `discontinuity` | One break in one aircraft's stream of position reports. |
| `nominal` | Within the normal range for that receiver and channel. |
| `rate ratio` | The rate inside the window divided by the rate in the reference period. |
| `reference period` | The time outside the event window, used as the comparison for a rate. |
| `smoothing constant` | A small fixed number added to both sides of a rate comparison so that a division by zero cannot occur. |

---

## Evidence pack 00248 -- 1 of 20

| | |
|---|---|
| **When** | 2022-06-27 12:31 to 12:36 |
| **Where** | RF-06, RF-07 &middot; channel 4 |

### The conclusion being explained

> the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption.
>
> *FUSION-SPATIAL / possible_interference_zone* &middot; RF-06, RF-07

### The evidence behind it

**RF-NOISE / rf_noise_deviation** &middot; 8 findings

power_dbm deviated by ... dB at its peak

| Source | |
|---|---|
| RF-06:4 | 9.51 &middot; 11.62 &middot; 11.45 &middot; 8.81 |
| RF-07:4 | 8.51 &middot; 11.63 &middot; 10.91 &middot; 12.76 |

**TRACK-GAP / track_rate_excess** &middot; 1 finding

**60 km disc** -- 4 discontinuities during the window against 0 outside it, a rate ratio of 11.79

**TRACK-GAP / track_continuity_gap** &middot; 9 findings

reporting from this aircraft broke during the window

AC-13cbc9324e79 &middot; AC-17d744f0ebea &middot; AC-2b82be5f0101 &middot; AC-a8823f7a2d0d &middot; AC-d57a21bd0b31 &middot; AC-d834848b9fb1 (x2) &middot; AC-e63feaae09bb &middot; AC-ef10a00a0296

### What the rules could not determine

- **track** -- the local discontinuity rate could not be measured: the reference period outside this window held no track findings, so the ratio would consist of nothing but the smoothing constant and is not a comparison of two observed rates. This is the majority case, and it means the aircraft side neither supports nor contradicts the radio evidence here.
- **RF-07:4** -- (raised 3 times) a deviation on channel 4 of RF-07 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

### Hypothesis A

**Possible interference zone at RF-06, RF-07**

Stated confidence: **Medium**

FUSION-SPATIAL reports possible interference zone at RF-06, RF-07 between 2022-06-27 12:31:22 and 12:36:52 UTC, on channel(s) 4. The rule states: the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption. Behind it are 19 evidence item(s) of 4 kind(s), with 4 recorded uncertainty(ies). This account restates what the detection rules found and adds nothing to it.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- 8 findings of this kind across 2 source(s) between 12:31:32 and 12:36:22; for example, RF-06:4: power_dbm deviated by 9.51 dB at its peak.
- **FUSION-SPATIAL / possible_interference_zone** -- RF-06, RF-07: the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption.
- **TRACK-GAP / track_rate_excess** -- 60 km disc: 4 discontinuities during the window against 0 outside it, a rate ratio of 11.79.
- **TRACK-GAP / track_continuity_gap** -- 9 findings of this kind across 8 source(s) between 12:30:24 and 12:38:50; for example, AC-13cbc9324e79: reporting from this aircraft broke during the window.

*Uncertainty:*

- the local discontinuity rate could not be measured: the reference period outside this window held no track findings, so the ratio would consist of nothing but the smoothing constant and is not a comparison of two observed rates. This is the majority case, and it means the aircraft side neither supports nor contradicts the radio evidence here.
- a deviation on channel 4 of RF-07 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-07 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-07 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

*Alternatives:*

- possible_sensor_fault: the deviation may be in the receivers rather than in the environment. The rule ruled this out because more than one receiver deviated together, so a common-mode failure -- a shared power supply, a shared clock, one configuration change applied to several units -- is the reading this does not exclude.
- something the rule set does not encode: these conclusions are drawn by deterministic rules that can only choose among the explanations they were written to distinguish, so an event unlike any of them is reported as whichever encoded explanation it most resembles.

*Recommended action:*

Corroborate the deviation at RF-06, RF-07 against a source outside this system -- a NOTAM, a spectrum-monitoring report, an operator log -- before treating it as interference in the environment. The aircraft side is not a clean negative here -- see the uncertainties -- so it should not be read as evidence against.

### Hypothesis B

**Possible Electromagnetic Interference Zone Affecting Multiple Aircraft Tracks and RF Sensors**

Stated confidence: **Medium**

During the specified window, both RF-06 and RF-07 sensors detected significant power deviations on channel 4, coinciding with a cluster of aircraft track reporting gaps within a 60 km radius. This pattern suggests a possible interference zone affecting both radio frequency monitoring and aircraft transponder reporting.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- Both RF-06 and RF-07 observed multiple power_dbm deviations on channel 4, with peak deviations ranging from 8.5 dB to 12.8 dB during the window.
- **TRACK-GAP / track_continuity_gap** -- Several aircraft (including AC-13cbc9324e79, AC-17d744f0ebea, AC-2b82be5f0101, AC-a8823f7a2d0d, AC-d57a21bd0b31, AC-d834848b9fb1, AC-e63feaae09bb, and AC-ef10a00a0296) experienced reporting gaps during the same period.
- **TRACK-GAP / track_rate_excess** -- There were 4 track discontinuities during the window and none outside it, yielding a rate ratio of 11.79 within a 60 km disc.

*Uncertainty:*

- The local discontinuity rate outside the window could not be measured, so the aircraft track evidence does not independently confirm or refute the radio findings.
- Some short-lived deviations on RF-07:4 were observed but did not meet the event threshold.

*Alternatives:*

- The observed track gaps could be due to unrelated aircraft or transponder issues rather than RF interference; this would require evidence of independent aircraft system faults during the window.
- The RF noise deviations could be caused by local equipment malfunction or environmental factors unrelated to intentional or external interference.

*Recommended action:*

Check for independent reports of interference or outages from aircraft operators and air traffic control during the window. Review maintenance logs for RF-06 and RF-07 to rule out sensor malfunction. If possible, corroborate with additional RF monitoring sources in the area.

---

## Evidence pack 00250 -- 2 of 20

| | |
|---|---|
| **When** | 2022-06-27 12:10 to 12:15 |
| **Where** | RF-05, RF-06, RF-07 &middot; channel 4 |

### The conclusion being explained

> track discontinuities ran 2.13 times their local rate during this window (4 inside against 3 outside), at or above the 1.58 the replication set
>
> *FUSION-SPATIAL / possible_interference_zone* &middot; RF-05, RF-06, RF-07

### The evidence behind it

**RF-NOISE / rf_noise_deviation** &middot; 10 findings

power_dbm deviated by ... dB at its peak

| Source | |
|---|---|
| RF-05:4 | 14.27 &middot; 8.06 &middot; 12.33 &middot; 11.35 |
| RF-06:4 | 11.79 &middot; 11.24 &middot; 11.09 |
| RF-07:4 | 10.63 &middot; 11.44 &middot; 11.61 |

**TRACK-GAP / track_rate_excess** &middot; 1 finding

**60 km disc** -- 4 discontinuities during the window against 3 outside it, a rate ratio of 2.13

**TRACK-GAP / track_continuity_gap** &middot; 14 findings

reporting from this aircraft broke during the window

AC-1cb8598779ad &middot; AC-60af3839251d &middot; AC-61d1a0c50ecd &middot; AC-7fe0246dd6aa &middot; AC-8be51c7c091c &middot; AC-8f8cdb56c96f &middot; AC-9ac925d04c44 (x3) &middot; AC-b21f734f5f47 &middot; AC-c9216688d494 (x3) &middot; AC-f66c16a03660

### What the rules could not determine

- **RF-05:4** -- a deviation on channel 4 of RF-05 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

### Hypothesis A

**Interference Zone Likely Caused Track Disruptions and Elevated RF Noise on Channel 4**

Stated confidence: **High**

Multiple sensors (RF-05, RF-06, RF-07) detected significant, corroborated RF noise deviations on channel 4, coinciding with a more than doubled rate of track discontinuities for several aircraft in the same area and time window. This pattern is consistent with a localized interference zone affecting both RF environment and aircraft reporting.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- RF-05, RF-06, and RF-07 all observed medium-severity power_dbm deviations (up to 14.27 dB) on channel 4 during the window.
- **FUSION-SPATIAL / possible_interference_zone** -- Track discontinuities ran 2.13 times their local rate during the window, corroborated across all three sensors.
- **TRACK-GAP / track_continuity_gap** -- Multiple aircraft (e.g., AC-1cb8598779ad, AC-60af3839251d, AC-61d1a0c50ecd, and others) experienced reporting gaps during the same period.

*Uncertainty:*

- A brief deviation on RF-05:4 lasted only 1 reading and was not called an event, indicating some short disturbances may not be fully captured.

*Alternatives:*

- The track discontinuities and RF noise could be due to unrelated sensor malfunctions or scheduled maintenance, but this is less likely given the spatial and temporal alignment across multiple independent sensors and aircraft.

*Recommended action:*

Check for external reports of interference or outages in the affected area and time window, and contact operators of RF-05, RF-06, and RF-07 to confirm no maintenance or faults occurred during the event.

### Hypothesis B

**Possible interference zone at RF-05, RF-06, RF-07**

Stated confidence: **High**

FUSION-SPATIAL reports possible interference zone at RF-05, RF-06, RF-07 between 2022-06-27 12:10:12 and 12:15:32 UTC, on channel(s) 4. The rule states: track discontinuities ran 2.13 times their local rate during this window (4 inside against 3 outside), at or above the 1.58 the replication set. Behind it are 26 evidence item(s) of 4 kind(s), with 1 recorded uncertainty(ies). This account restates what the detection rules found and adds nothing to it.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- 10 findings of this kind across 3 source(s) between 12:10:22 and 12:15:12; for example, RF-05:4: power_dbm deviated by 14.27 dB at its peak.
- **FUSION-SPATIAL / possible_interference_zone** -- RF-05, RF-06, RF-07: track discontinuities ran 2.13 times their local rate during this window (4 inside against 3 outside), at or above the 1.58 the replication set.
- **TRACK-GAP / track_rate_excess** -- 60 km disc: 4 discontinuities during the window against 3 outside it, a rate ratio of 2.13.
- **TRACK-GAP / track_continuity_gap** -- 14 findings of this kind across 10 source(s) between 12:06:52 and 12:18:20; for example, AC-1cb8598779ad: reporting from this aircraft broke during the window.

*Uncertainty:*

- a deviation on channel 4 of RF-05 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

*Alternatives:*

- possible_sensor_fault: the deviation may be in the receivers rather than in the environment. The rule ruled this out because more than one receiver deviated together, so a common-mode failure -- a shared power supply, a shared clock, one configuration change applied to several units -- is the reading this does not exclude.
- something the rule set does not encode: these conclusions are drawn by deterministic rules that can only choose among the explanations they were written to distinguish, so an event unlike any of them is reported as whichever encoded explanation it most resembles.

*Recommended action:*

Corroborate the deviation at RF-05, RF-06, RF-07 against a source outside this system -- a NOTAM, a spectrum-monitoring report, an operator log -- before treating it as interference in the environment.

---

## Evidence pack 00252 -- 3 of 20

| | |
|---|---|
| **When** | 2022-06-27 12:38 to 12:43 |
| **Where** | RF-01, RF-02, RF-03 &middot; channel 4 |

### The conclusion being explained

> the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption.
>
> *FUSION-SPATIAL / possible_interference_zone* &middot; RF-01, RF-02, RF-03

### The evidence behind it

**RF-NOISE / rf_noise_deviation** &middot; 14 findings

power_dbm deviated by ... dB at its peak

| Source | |
|---|---|
| RF-01:4 | 13.43 &middot; 10.62 &middot; 8.37 &middot; 9.20 &middot; 14.95 |
| RF-02:4 | 8.53 &middot; 10.90 &middot; 8.58 &middot; 9.64 &middot; 11.11 |
| RF-03:4 | 11.18 &middot; 9.28 &middot; 9.86 &middot; 8.46 |

**TRACK-GAP / track_rate_excess** &middot; 1 finding

**60 km disc** -- 6 discontinuities during the window against 0 outside it, a rate ratio of 18.23

**TRACK-GAP / track_continuity_gap** &middot; 14 findings

reporting from this aircraft broke during the window

AC-0ced9601dd53 &middot; AC-195d53328027 &middot; AC-38fa046f093c &middot; AC-6070168602bf &middot; AC-6d57956aee92 (x2) &middot; AC-85a9bcf7e274 &middot; AC-95c06f5715b6 &middot; AC-b92c8fe3d0f0 &middot; AC-c6191e183fc9 &middot; AC-d834848b9fb1 &middot; AC-f65bb79d61e9 (x2) &middot; AC-f68b84990035

### What the rules could not determine

- **track** -- the local discontinuity rate could not be measured: the reference period outside this window held no track findings, so the ratio would consist of nothing but the smoothing constant and is not a comparison of two observed rates. This is the majority case, and it means the aircraft side neither supports nor contradicts the radio evidence here.
- **a deviation on channel 4 of ... lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.**
  RF-01 &middot; RF-02 (x2) &middot; RF-03 (x3)

### Hypothesis A

**Possible interference zone at RF-01, RF-02, RF-03**

Stated confidence: **Medium**

FUSION-SPATIAL reports possible interference zone at RF-01, RF-02, RF-03 between 2022-06-27 12:38:30 and 12:43:40 UTC, on channel(s) 4. The rule states: the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption. Behind it are 30 evidence item(s) of 4 kind(s), with 7 recorded uncertainty(ies). This account restates what the detection rules found and adds nothing to it.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- 14 findings of this kind across 3 source(s) between 12:38:50 and 12:43:40; for example, RF-01:4: power_dbm deviated by 13.43 dB at its peak.
- **FUSION-SPATIAL / possible_interference_zone** -- RF-01, RF-02, RF-03: the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption.
- **TRACK-GAP / track_rate_excess** -- 60 km disc: 6 discontinuities during the window against 0 outside it, a rate ratio of 18.23.
- **TRACK-GAP / track_continuity_gap** -- 14 findings of this kind across 12 source(s) between 12:28:48 and 12:51:40; for example, AC-0ced9601dd53: reporting from this aircraft broke during the window.

*Uncertainty:*

- the local discontinuity rate could not be measured: the reference period outside this window held no track findings, so the ratio would consist of nothing but the smoothing constant and is not a comparison of two observed rates. This is the majority case, and it means the aircraft side neither supports nor contradicts the radio evidence here.
- a deviation on channel 4 of RF-01 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-02 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-02 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-03 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-03 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-03 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

*Alternatives:*

- possible_sensor_fault: the deviation may be in the receivers rather than in the environment. The rule ruled this out because more than one receiver deviated together, so a common-mode failure -- a shared power supply, a shared clock, one configuration change applied to several units -- is the reading this does not exclude.
- something the rule set does not encode: these conclusions are drawn by deterministic rules that can only choose among the explanations they were written to distinguish, so an event unlike any of them is reported as whichever encoded explanation it most resembles.

*Recommended action:*

Corroborate the deviation at RF-01, RF-02, RF-03 against a source outside this system -- a NOTAM, a spectrum-monitoring report, an operator log -- before treating it as interference in the environment. The aircraft side is not a clean negative here -- see the uncertainties -- so it should not be read as evidence against.

### Hypothesis B

**Interference Zone Likely Caused Track Disruptions and RF Noise on Channel 4**

Stated confidence: **Medium**

During the specified window, multiple sensors (RF-01, RF-02, RF-03) detected significant power deviations on channel 4, and there was a marked increase in track reporting gaps from several aircraft within the affected area. This pattern is consistent with a localized interference event impacting both RF noise levels and aircraft track continuity.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- All three sensors (RF-01, RF-02, RF-03) observed multiple, significant power_dbm deviations on channel 4 during the window.
- **TRACK-GAP / track_rate_excess** -- There were 6 track discontinuities during the window and none outside it, indicating a sharp increase in reporting gaps.
- **TRACK-GAP / track_continuity_gap** -- Several aircraft (e.g., AC-0ced9601dd53, AC-195d53328027, AC-38fa046f093c, and others) experienced reporting gaps during the window, with frozen positions recorded.

*Uncertainty:*

- The local discontinuity rate could not be measured outside the window, so the track evidence does not independently confirm or contradict the RF findings.
- Some short RF deviations were observed but not called events due to their duration being under the 10 s minimum.

*Alternatives:*

- The observed track gaps could be due to unrelated technical issues with the aircraft or ground systems, not RF interference. To support this, one would need evidence of similar disruptions outside the interference window or on other channels.

*Recommended action:*

Check for independent reports of interference or technical issues from aircraft operators or ground control during the window. Review logs for maintenance or outages affecting the affected aircraft or sensors.

---

## Evidence pack 00253 -- 4 of 20

| | |
|---|---|
| **When** | 2022-06-27 12:38 to 12:43 |
| **Where** | RF-06, RF-07 &middot; channel 4 |

### The conclusion being explained

> the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption.
>
> *FUSION-SPATIAL / possible_interference_zone* &middot; RF-06, RF-07

### The evidence behind it

**RF-NOISE / rf_noise_deviation** &middot; 9 findings

power_dbm deviated by ... dB at its peak

| Source | |
|---|---|
| RF-06:4 | 13.50 &middot; 10.25 &middot; 7.07 &middot; 13.59 &middot; 10.17 &middot; 9.47 |
| RF-07:4 | 11.65 &middot; 8.72 &middot; 13.20 |

**TRACK-GAP / track_rate_excess** &middot; 1 finding

**60 km disc** -- 4 discontinuities during the window against 0 outside it, a rate ratio of 11.47

**TRACK-GAP / track_continuity_gap** &middot; 15 findings

reporting from this aircraft broke during the window

AC-0ced9601dd53 &middot; AC-195d53328027 &middot; AC-38fa046f093c &middot; AC-5b705c3f3d6a &middot; AC-6070168602bf &middot; AC-6d57956aee92 (x2) &middot; AC-85a9bcf7e274 &middot; AC-b726526b14f6 &middot; AC-d834848b9fb1 &middot; AC-dbf042c707b1 (x2) &middot; AC-e422e702fa25 &middot; AC-f65bb79d61e9 (x2)

### What the rules could not determine

- **track** -- the local discontinuity rate could not be measured: the reference period outside this window held no track findings, so the ratio would consist of nothing but the smoothing constant and is not a comparison of two observed rates. This is the majority case, and it means the aircraft side neither supports nor contradicts the radio evidence here.
- **RF-06:4** -- a deviation on channel 4 of RF-06 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

### Hypothesis A

**Probable Localized RF Interference Zone Affecting Aircraft Track Reporting**

Stated confidence: **Medium**

During the specified window, both RF-06 and RF-07 observed significant deviations in power levels on channel 4, coinciding with a sharp increase in aircraft track reporting gaps within the affected area. This pattern is consistent with a localized RF interference event disrupting aircraft transponder or communication signals.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- Both RF-06 and RF-07 recorded multiple significant power_dbm deviations (up to ~13 dB) on channel 4 during the window, indicating abnormal RF noise.
- **TRACK-GAP / track_rate_excess** -- A 60 km disc around the affected area showed 4 track discontinuities during the window and none outside it, yielding a rate ratio of 11.47.
- **TRACK-GAP / track_continuity_gap** -- Multiple aircraft (e.g., AC-0ced9601dd53, AC-195d53328027, AC-38fa046f093c, and others) experienced reporting gaps during the same period, with 'frozen position' shapes indicating loss of track updates.

*Uncertainty:*

- The local discontinuity rate outside the window could not be measured, so the track evidence does not independently confirm or contradict the RF findings.
- A brief deviation on RF-06:4 lasted only 1 reading and was not called an event.

*Alternatives:*

- The observed track reporting gaps could be due to unrelated aircraft or system issues rather than RF interference; this would require evidence of unrelated technical faults or maintenance events affecting multiple aircraft simultaneously.

*Recommended action:*

Check for independent reports of RF interference or communication outages from air traffic control or operators in the affected area during the window. Review maintenance logs for the involved aircraft to rule out unrelated technical issues.

### Hypothesis B

**Possible interference zone at RF-06, RF-07**

Stated confidence: **Medium**

FUSION-SPATIAL reports possible interference zone at RF-06, RF-07 between 2022-06-27 12:38:11 and 12:43:51 UTC, on channel(s) 4. The rule states: the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption. Behind it are 26 evidence item(s) of 4 kind(s), with 2 recorded uncertainty(ies). This account restates what the detection rules found and adds nothing to it.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- 9 findings of this kind across 2 source(s) between 12:38:41 and 12:43:31; for example, RF-06:4: power_dbm deviated by 13.50 dB at its peak.
- **FUSION-SPATIAL / possible_interference_zone** -- RF-06, RF-07: the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption.
- **TRACK-GAP / track_rate_excess** -- 60 km disc: 4 discontinuities during the window against 0 outside it, a rate ratio of 11.47.
- **TRACK-GAP / track_continuity_gap** -- 15 findings of this kind across 12 source(s) between 12:28:48 and 12:51:40; for example, AC-0ced9601dd53: reporting from this aircraft broke during the window.

*Uncertainty:*

- the local discontinuity rate could not be measured: the reference period outside this window held no track findings, so the ratio would consist of nothing but the smoothing constant and is not a comparison of two observed rates. This is the majority case, and it means the aircraft side neither supports nor contradicts the radio evidence here.
- a deviation on channel 4 of RF-06 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

*Alternatives:*

- possible_sensor_fault: the deviation may be in the receivers rather than in the environment. The rule ruled this out because more than one receiver deviated together, so a common-mode failure -- a shared power supply, a shared clock, one configuration change applied to several units -- is the reading this does not exclude.
- something the rule set does not encode: these conclusions are drawn by deterministic rules that can only choose among the explanations they were written to distinguish, so an event unlike any of them is reported as whichever encoded explanation it most resembles.

*Recommended action:*

Corroborate the deviation at RF-06, RF-07 against a source outside this system -- a NOTAM, a spectrum-monitoring report, an operator log -- before treating it as interference in the environment. The aircraft side is not a clean negative here -- see the uncertainties -- so it should not be read as evidence against.

---

## Evidence pack 00254 -- 5 of 20

| | |
|---|---|
| **When** | 2022-06-27 12:23 to 12:28 |
| **Where** | RF-01, RF-02, RF-03 &middot; channel 4 |

### The conclusion being explained

> the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption.
>
> *FUSION-SPATIAL / possible_interference_zone* &middot; RF-01, RF-02, RF-03

### The evidence behind it

**RF-NOISE / rf_noise_deviation** &middot; 16 findings

power_dbm deviated by ... dB at its peak

| Source | |
|---|---|
| RF-01:4 | 10.62 &middot; 9.16 &middot; 8.73 &middot; 14.11 &middot; 8.60 &middot; 10.51 &middot; 9.27 |
| RF-02:4 | 11.01 &middot; 10.25 &middot; 10.83 &middot; 11.46 &middot; 10.31 |
| RF-03:4 | 8.96 &middot; 11.47 &middot; 11.04 &middot; 10.65 |

**TRACK-GAP / track_rate_excess** &middot; 1 finding

**60 km disc** -- 4 discontinuities during the window against 0 outside it, a rate ratio of 11.47

**TRACK-GAP / track_continuity_gap** &middot; 9 findings

reporting from this aircraft broke during the window

AC-01df46f171f3 &middot; AC-195d53328027 &middot; AC-3ae425dee296 &middot; AC-78979e3b3ff3 &middot; AC-9c923c64bcc2 &middot; AC-c157c480dc72 &middot; AC-caa163be23a6 &middot; AC-d834848b9fb1 &middot; AC-dda8a23ab2cc

### What the rules could not determine

- **track** -- the local discontinuity rate could not be measured: the reference period outside this window held no track findings, so the ratio would consist of nothing but the smoothing constant and is not a comparison of two observed rates. This is the majority case, and it means the aircraft side neither supports nor contradicts the radio evidence here.
- **a deviation on channel 4 of ... lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.**
  RF-01 &middot; RF-02 &middot; RF-03

### Hypothesis A

**Possible interference zone at RF-01, RF-02, RF-03**

Stated confidence: **Medium**

FUSION-SPATIAL reports possible interference zone at RF-01, RF-02, RF-03 between 2022-06-27 12:23:19 and 12:28:59 UTC, on channel(s) 4. The rule states: the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption. Behind it are 27 evidence item(s) of 4 kind(s), with 4 recorded uncertainty(ies). This account restates what the detection rules found and adds nothing to it.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- 16 findings of this kind across 3 source(s) between 12:23:49 and 12:28:39; for example, RF-01:4: power_dbm deviated by 10.62 dB at its peak.
- **FUSION-SPATIAL / possible_interference_zone** -- RF-01, RF-02, RF-03: the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption.
- **TRACK-GAP / track_rate_excess** -- 60 km disc: 4 discontinuities during the window against 0 outside it, a rate ratio of 11.47.
- **TRACK-GAP / track_continuity_gap** -- 9 findings of this kind across 9 source(s) between 12:21:08 and 12:33:30; for example, AC-01df46f171f3: reporting from this aircraft broke during the window.

*Uncertainty:*

- the local discontinuity rate could not be measured: the reference period outside this window held no track findings, so the ratio would consist of nothing but the smoothing constant and is not a comparison of two observed rates. This is the majority case, and it means the aircraft side neither supports nor contradicts the radio evidence here.
- a deviation on channel 4 of RF-01 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-02 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-03 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

*Alternatives:*

- possible_sensor_fault: the deviation may be in the receivers rather than in the environment. The rule ruled this out because more than one receiver deviated together, so a common-mode failure -- a shared power supply, a shared clock, one configuration change applied to several units -- is the reading this does not exclude.
- something the rule set does not encode: these conclusions are drawn by deterministic rules that can only choose among the explanations they were written to distinguish, so an event unlike any of them is reported as whichever encoded explanation it most resembles.

*Recommended action:*

Corroborate the deviation at RF-01, RF-02, RF-03 against a source outside this system -- a NOTAM, a spectrum-monitoring report, an operator log -- before treating it as interference in the environment. The aircraft side is not a clean negative here -- see the uncertainties -- so it should not be read as evidence against.

### Hypothesis B

**Interference Zone Likely on Channel 4 During Window**

Stated confidence: **Medium**

Multiple sensors (RF-01, RF-02, RF-03) detected significant, repeated power deviations on channel 4 during the specified window, and several aircraft experienced track reporting gaps in the same period and area. This pattern is consistent with a localized interference event affecting both RF sensors and aircraft tracking.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- All three RF sensors (RF-01, RF-02, RF-03) observed repeated, significant power_dbm deviations on channel 4 during the window.
- **TRACK-GAP / track_continuity_gap** -- Multiple aircraft (e.g., AC-01df46f171f3, AC-195d53328027, AC-3ae425dee296, AC-78979e3b3ff3, AC-9c923c64bcc2, AC-c157c480dc72, AC-caa163be23a6, AC-d834848b9fb1) experienced reporting gaps during the same window.
- **TRACK-GAP / track_rate_excess** -- There were 4 track discontinuities during the window and none outside it, indicating a sharp increase in reporting failures.

*Uncertainty:*

- The local discontinuity rate could not be measured outside the window, so the aircraft track evidence does not independently confirm the radio findings.
- Short deviations on channel 4 of RF-01, RF-02, and RF-03 were observed but not called events due to their brief duration.

*Alternatives:*

- The observed track reporting gaps could be due to unrelated technical issues with the aircraft or ground systems rather than RF interference. To support this, one would need evidence of system faults or maintenance during the window.

*Recommended action:*

Check for external reports of interference or outages in the affected area and time, and contact operators of the affected aircraft to determine if they experienced technical issues unrelated to RF conditions.

---

## Evidence pack 00255 -- 6 of 20

| | |
|---|---|
| **When** | 2022-06-27 12:30 to 12:36 |
| **Where** | RF-01, RF-03 &middot; channel 4 |

### The conclusion being explained

> the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption.
>
> *FUSION-SPATIAL / possible_interference_zone* &middot; RF-01, RF-03

### The evidence behind it

**RF-NOISE / rf_noise_deviation** &middot; 10 findings

power_dbm deviated by ... dB at its peak

| Source | |
|---|---|
| RF-01:4 | 9.95 &middot; 9.15 &middot; 12.47 &middot; 11.64 &middot; 10.55 |
| RF-03:4 | 9.23 &middot; 8.75 &middot; 11.30 &middot; 12.66 &middot; 11.15 |

**TRACK-GAP / track_rate_excess** &middot; 1 finding

**60 km disc** -- 4 discontinuities during the window against 0 outside it, a rate ratio of 11.47

**TRACK-GAP / track_continuity_gap** &middot; 10 findings

reporting from this aircraft broke during the window

AC-195d53328027 &middot; AC-3ae425dee296 &middot; AC-604973b41bd3 &middot; AC-8fdbb17abd75 &middot; AC-9d3106afb475 &middot; AC-a8823f7a2d0d &middot; AC-caa163be23a6 &middot; AC-d57a21bd0b31 &middot; AC-d834848b9fb1 &middot; AC-e63feaae09bb

### What the rules could not determine

- **track** -- the local discontinuity rate could not be measured: the reference period outside this window held no track findings, so the ratio would consist of nothing but the smoothing constant and is not a comparison of two observed rates. This is the majority case, and it means the aircraft side neither supports nor contradicts the radio evidence here.
- **a deviation on channel 4 of ... lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.**
  RF-01 &middot; RF-03 (x2)

### Hypothesis A

**Probable Localized RF Interference Zone Affecting Channel 4**

Stated confidence: **Medium**

Multiple significant deviations in RF power were observed on channel 4 by both RF-01 and RF-03 during the window, coinciding with a cluster of track continuity gaps from several aircraft. This pattern suggests a localized interference event affecting both radio sensors and aircraft reporting within the area.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- Both RF-01 and RF-03 recorded multiple power_dbm deviations on channel 4, with peaks exceeding 10 dB and durations up to several minutes.
- **TRACK-GAP / track_rate_excess** -- A 60 km disc around the affected area saw 4 track discontinuities during the window and none outside it, indicating a sharp increase in reporting gaps.
- **TRACK-GAP / track_continuity_gap** -- Several aircraft (e.g., AC-195d53328027, AC-3ae425dee296, AC-604973b41bd3, AC-8fdbb17abd75, AC-9d3106afb475, AC-a8823f7a2d0d, AC-caa163be23a6, AC-d57a21bd0b31, AC-d834848b9fb1, AC-e63feaae09bb) experienced reporting gaps during the same period.

*Uncertainty:*

- The local discontinuity rate could not be measured outside the window due to a lack of track findings, so the aircraft-side evidence neither supports nor contradicts the radio evidence.
- Some observed RF deviations on channel 4 of RF-01 and RF-03 were too brief (under 10 s) to be called events.

*Alternatives:*

- The observed track gaps could be due to unrelated technical issues with the aircraft or ground systems rather than RF interference. This would require independent confirmation that no interference was present during the window.

*Recommended action:*

Check for independent reports of RF interference or technical issues from aircraft operators or ground control in the affected area and time window.

### Hypothesis B

**Possible interference zone at RF-01, RF-03**

Stated confidence: **Medium**

FUSION-SPATIAL reports possible interference zone at RF-01, RF-03 between 2022-06-27 12:30:24 and 12:36:04 UTC, on channel(s) 4. The rule states: the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption. Behind it are 22 evidence item(s) of 4 kind(s), with 4 recorded uncertainty(ies). This account restates what the detection rules found and adds nothing to it.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- 10 findings of this kind across 2 source(s) between 12:31:04 and 12:35:54; for example, RF-01:4: power_dbm deviated by 9.95 dB at its peak.
- **FUSION-SPATIAL / possible_interference_zone** -- RF-01, RF-03: the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption.
- **TRACK-GAP / track_rate_excess** -- 60 km disc: 4 discontinuities during the window against 0 outside it, a rate ratio of 11.47.
- **TRACK-GAP / track_continuity_gap** -- 10 findings of this kind across 10 source(s) between 12:27:46 and 12:37:40; for example, AC-195d53328027: reporting from this aircraft broke during the window.

*Uncertainty:*

- the local discontinuity rate could not be measured: the reference period outside this window held no track findings, so the ratio would consist of nothing but the smoothing constant and is not a comparison of two observed rates. This is the majority case, and it means the aircraft side neither supports nor contradicts the radio evidence here.
- a deviation on channel 4 of RF-01 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-03 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-03 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

*Alternatives:*

- possible_sensor_fault: the deviation may be in the receivers rather than in the environment. The rule ruled this out because more than one receiver deviated together, so a common-mode failure -- a shared power supply, a shared clock, one configuration change applied to several units -- is the reading this does not exclude.
- something the rule set does not encode: these conclusions are drawn by deterministic rules that can only choose among the explanations they were written to distinguish, so an event unlike any of them is reported as whichever encoded explanation it most resembles.

*Recommended action:*

Corroborate the deviation at RF-01, RF-03 against a source outside this system -- a NOTAM, a spectrum-monitoring report, an operator log -- before treating it as interference in the environment. The aircraft side is not a clean negative here -- see the uncertainties -- so it should not be read as evidence against.

---

## Evidence pack 00256 -- 7 of 20

| | |
|---|---|
| **When** | 2022-06-27 12:36 to 12:41 |
| **Where** | RF-01, RF-02, RF-03 &middot; channel 4 |

### The conclusion being explained

> the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption.
>
> *FUSION-SPATIAL / possible_interference_zone* &middot; RF-01, RF-02, RF-03

### The evidence behind it

**RF-NOISE / rf_noise_deviation** &middot; 10 findings

power_dbm deviated by ... dB at its peak

| Source | |
|---|---|
| RF-01:4 | 11.83 &middot; 14.92 &middot; 11.57 &middot; 12.85 |
| RF-02:4 | 13.20 &middot; 12.20 |
| RF-03:4 | 15.75 &middot; 12.26 &middot; 9.45 &middot; 11.02 |

**TRACK-GAP / track_rate_excess** &middot; 1 finding

**60 km disc** -- 3 discontinuities during the window against 0 outside it, a rate ratio of 8.85

**TRACK-GAP / track_continuity_gap** &middot; 14 findings

reporting from this aircraft broke during the window

AC-0ced9601dd53 &middot; AC-195d53328027 &middot; AC-19fea31858d7 &middot; AC-1ac8c6bd2227 &middot; AC-38fa046f093c &middot; AC-6070168602bf &middot; AC-6d57956aee92 (x2) &middot; AC-85a9bcf7e274 &middot; AC-a8823f7a2d0d &middot; AC-caa163be23a6 &middot; AC-d055f9d31e52 &middot; AC-d834848b9fb1 (x2)

### What the rules could not determine

- **track** -- the local discontinuity rate could not be measured: the reference period outside this window held no track findings, so the ratio would consist of nothing but the smoothing constant and is not a comparison of two observed rates. This is the majority case, and it means the aircraft side neither supports nor contradicts the radio evidence here.
- **a deviation on channel 4 of ... lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.**
  RF-02 (x4) &middot; RF-03 (x2)

### Hypothesis A

**Possible interference zone at RF-01, RF-02, RF-03**

Stated confidence: **Medium**

FUSION-SPATIAL reports possible interference zone at RF-01, RF-02, RF-03 between 2022-06-27 12:36:05 and 12:41:45 UTC, on channel(s) 4. The rule states: the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption. Behind it are 26 evidence item(s) of 4 kind(s), with 7 recorded uncertainty(ies). This account restates what the detection rules found and adds nothing to it.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- 10 findings of this kind across 3 source(s) between 12:36:15 and 12:41:05; for example, RF-01:4: power_dbm deviated by 11.83 dB at its peak.
- **FUSION-SPATIAL / possible_interference_zone** -- RF-01, RF-02, RF-03: the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption.
- **TRACK-GAP / track_rate_excess** -- 60 km disc: 3 discontinuities during the window against 0 outside it, a rate ratio of 8.85.
- **TRACK-GAP / track_continuity_gap** -- 14 findings of this kind across 12 source(s) between 12:34:21 and 12:44:50; for example, AC-0ced9601dd53: reporting from this aircraft broke during the window.

*Uncertainty:*

- the local discontinuity rate could not be measured: the reference period outside this window held no track findings, so the ratio would consist of nothing but the smoothing constant and is not a comparison of two observed rates. This is the majority case, and it means the aircraft side neither supports nor contradicts the radio evidence here.
- a deviation on channel 4 of RF-02 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-02 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-02 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-02 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-03 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-03 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

*Alternatives:*

- possible_sensor_fault: the deviation may be in the receivers rather than in the environment. The rule ruled this out because more than one receiver deviated together, so a common-mode failure -- a shared power supply, a shared clock, one configuration change applied to several units -- is the reading this does not exclude.
- something the rule set does not encode: these conclusions are drawn by deterministic rules that can only choose among the explanations they were written to distinguish, so an event unlike any of them is reported as whichever encoded explanation it most resembles.

*Recommended action:*

Corroborate the deviation at RF-01, RF-02, RF-03 against a source outside this system -- a NOTAM, a spectrum-monitoring report, an operator log -- before treating it as interference in the environment. The aircraft side is not a clean negative here -- see the uncertainties -- so it should not be read as evidence against.

### Hypothesis B

**Interference Zone Likely Affected Channel 4 in Area Around 52.24N, 4.91E**

Stated confidence: **Medium**

Multiple sensors (RF-01, RF-02, RF-03) detected significant, sustained RF noise deviations on channel 4 during the window, coinciding with a cluster of aircraft track reporting gaps in the same period and area. This pattern is consistent with a localized interference event affecting both RF environment and aircraft reporting.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- All three sensors (RF-01, RF-02, RF-03) observed medium to high power_dbm deviations on channel 4, with peaks ranging from 9.45 dB to 15.75 dB, sustained over multiple readings during the alert window.
- **TRACK-GAP / track_rate_excess** -- A 60 km disc around the affected area showed 3 track discontinuities during the window and none outside it, yielding a rate ratio of 8.85.
- **TRACK-GAP / track_continuity_gap** -- Several aircraft (e.g., AC-0ced9601dd53, AC-195d53328027, AC-19fea31858d7, AC-1ac8c6bd2227, AC-38fa046f093c, AC-6070168602bf, AC-6d57956aee92, AC-85a9bcf7e274, AC-a8823f7a2d0d, AC-caa163be23a6, AC-d055f9d31e52, AC-d834848b9fb1) experienced reporting gaps (frozen positions) overlapping the RF noise events.

*Uncertainty:*

- The local discontinuity rate could not be measured outside the window due to no track findings, so the aircraft-side evidence neither supports nor contradicts the RF evidence.
- Some short RF deviations on RF-02:4 and RF-03:4 were observed but did not meet the event threshold (under 10 s), so were not counted as events.

*Alternatives:*

- Aircraft reporting gaps could be due to unrelated technical issues or scheduled maintenance, but the temporal and spatial clustering with RF noise deviations makes this less likely. To support this alternative, evidence of unrelated outages or maintenance logs would be needed.

*Recommended action:*

Check for external reports of RF interference or outages in the area and time window, and contact operators of affected aircraft for any technical issues or maintenance that could explain the reporting gaps.

---

## Evidence pack 00259 -- 8 of 20

| | |
|---|---|
| **When** | 2022-06-27 12:09 to 12:14 |
| **Where** | RF-04, RF-05 &middot; channel 4 |

### The conclusion being explained

> the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption.
>
> *FUSION-SPATIAL / possible_interference_zone* &middot; RF-04, RF-05

### The evidence behind it

**RF-NOISE / rf_noise_deviation** &middot; 8 findings

power_dbm deviated by ... dB at its peak

| Source | |
|---|---|
| RF-04:4 | 11.58 &middot; 10.66 &middot; 10.93 &middot; 8.89 &middot; 10.60 |
| RF-05:4 | 9.70 &middot; 11.29 &middot; 13.53 |

**TRACK-GAP / track_rate_excess** &middot; 1 finding

**60 km disc** -- 6 discontinuities during the window against 0 outside it, a rate ratio of 18.23

**TRACK-GAP / track_continuity_gap** &middot; 17 findings

reporting from this aircraft broke during the window

AC-1cb8598779ad &middot; AC-60af3839251d &middot; AC-61d1a0c50ecd &middot; AC-6647e5864ec5 &middot; AC-75672d5dc92e &middot; AC-7fe0246dd6aa &middot; AC-9799698a3148 &middot; AC-9ac925d04c44 (x5) &middot; AC-b62a82cb4cb9 &middot; AC-c9216688d494 (x3) &middot; AC-f0f13c34444b

### What the rules could not determine

- **track** -- the local discontinuity rate could not be measured: the reference period outside this window held no track findings, so the ratio would consist of nothing but the smoothing constant and is not a comparison of two observed rates. This is the majority case, and it means the aircraft side neither supports nor contradicts the radio evidence here.
- **RF-05:4** -- (raised 2 times) a deviation on channel 4 of RF-05 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

### Hypothesis A

**Probable RF Interference Zone Affecting Channel 4 Near (51.5262, 5.75835)**

Stated confidence: **Medium**

Multiple significant power deviations on channel 4 were observed by both RF-04 and RF-05 during the window, coinciding with a sharp increase in track reporting discontinuities from several aircraft in the area. This pattern is consistent with a localized RF interference event affecting both sensors and aircraft reporting.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- Both RF-04 and RF-05 recorded repeated, significant power_dbm deviations (up to 13.53 dB) on channel 4 during the window.
- **TRACK-GAP / track_rate_excess** -- A 60 km disc around the area showed 6 track discontinuities during the window and none outside it, indicating a strong temporal association.
- **TRACK-GAP / track_continuity_gap** -- Several aircraft (e.g., AC-1cb8598779ad, AC-60af3839251d, AC-61d1a0c50ecd, and others) experienced reporting gaps overlapping the RF noise events.

*Uncertainty:*

- The local discontinuity rate outside the window could not be measured, so the aircraft-side evidence does not independently confirm the radio findings.
- Some short RF-05:4 deviations were observed but not called events due to duration under 10 seconds.

*Alternatives:*

- Aircraft reporting gaps could be due to unrelated technical issues or scheduled maintenance, but the temporal and spatial clustering with RF noise makes this less likely. To support this alternative, evidence of unrelated outages or maintenance logs would be needed.
- Environmental or atmospheric effects could cause both RF noise and track gaps, though the repeated, channel-specific deviations suggest a more localized interference source.

*Recommended action:*

Check for known sources of RF interference or maintenance activity in the affected area and time window. Seek independent confirmation from other RF monitoring systems or ground reports.

### Hypothesis B

**Possible interference zone at RF-04, RF-05**

Stated confidence: **Medium**

FUSION-SPATIAL reports possible interference zone at RF-04, RF-05 between 2022-06-27 12:09:46 and 12:14:56 UTC, on channel(s) 4. The rule states: the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption. Behind it are 27 evidence item(s) of 4 kind(s), with 3 recorded uncertainty(ies). This account restates what the detection rules found and adds nothing to it.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- 8 findings of this kind across 2 source(s) between 12:09:56 and 12:14:46; for example, RF-04:4: power_dbm deviated by 11.58 dB at its peak.
- **FUSION-SPATIAL / possible_interference_zone** -- RF-04, RF-05: the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption.
- **TRACK-GAP / track_rate_excess** -- 60 km disc: 6 discontinuities during the window against 0 outside it, a rate ratio of 18.23.
- **TRACK-GAP / track_continuity_gap** -- 17 findings of this kind across 11 source(s) between 12:06:10 and 12:18:20; for example, AC-1cb8598779ad: reporting from this aircraft broke during the window.

*Uncertainty:*

- the local discontinuity rate could not be measured: the reference period outside this window held no track findings, so the ratio would consist of nothing but the smoothing constant and is not a comparison of two observed rates. This is the majority case, and it means the aircraft side neither supports nor contradicts the radio evidence here.
- a deviation on channel 4 of RF-05 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-05 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

*Alternatives:*

- possible_sensor_fault: the deviation may be in the receivers rather than in the environment. The rule ruled this out because more than one receiver deviated together, so a common-mode failure -- a shared power supply, a shared clock, one configuration change applied to several units -- is the reading this does not exclude.
- something the rule set does not encode: these conclusions are drawn by deterministic rules that can only choose among the explanations they were written to distinguish, so an event unlike any of them is reported as whichever encoded explanation it most resembles.

*Recommended action:*

Corroborate the deviation at RF-04, RF-05 against a source outside this system -- a NOTAM, a spectrum-monitoring report, an operator log -- before treating it as interference in the environment. The aircraft side is not a clean negative here -- see the uncertainties -- so it should not be read as evidence against.

---

## Evidence pack 00262 -- 9 of 20

| | |
|---|---|
| **When** | 2022-06-27 12:24 to 12:30 |
| **Where** | RF-04, RF-05 &middot; channel 4 |

### The conclusion being explained

> the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption.
>
> *FUSION-SPATIAL / possible_interference_zone* &middot; RF-04, RF-05

### The evidence behind it

**RF-NOISE / rf_noise_deviation** &middot; 7 findings

power_dbm deviated by ... dB at its peak

| Source | |
|---|---|
| RF-04:4 | 12.30 &middot; 7.43 &middot; 9.98 &middot; 10.59 |
| RF-05:4 | 10.51 &middot; 11.43 &middot; 12.67 |

**TRACK-GAP / track_rate_excess** &middot; 1 finding

**60 km disc** -- 3 discontinuities during the window against 0 outside it, a rate ratio of 9.09

**TRACK-GAP / track_continuity_gap** &middot; 8 findings

reporting from this aircraft broke during the window

AC-01df46f171f3 &middot; AC-06ce04b438f6 &middot; AC-195d53328027 &middot; AC-19fea31858d7 &middot; AC-7466d670a158 &middot; AC-c157c480dc72 &middot; AC-d834848b9fb1 &middot; AC-dc9c0d886a85

### What the rules could not determine

- **track** -- the local discontinuity rate could not be measured: the reference period outside this window held no track findings, so the ratio would consist of nothing but the smoothing constant and is not a comparison of two observed rates. This is the majority case, and it means the aircraft side neither supports nor contradicts the radio evidence here.
- **RF-05:4** -- (raised 3 times) a deviation on channel 4 of RF-05 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

### Hypothesis A

**Possible RF Interference Zone Affecting Channel 4 Near (51.5262, 5.75835)**

Stated confidence: **Medium**

Multiple significant power deviations were observed on channel 4 by both RF-04 and RF-05 during the window, coinciding with a cluster of track reporting gaps from several aircraft. This pattern is consistent with a localized RF interference event affecting the area.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- Both RF-04 and RF-05 recorded multiple power_dbm deviations on channel 4, with peaks exceeding 10 dB, during the window.
- **TRACK-GAP / track_continuity_gap** -- Several aircraft (including AC-01df46f171f3, AC-06ce04b438f6, AC-195d53328027, AC-19fea31858d7, AC-7466d670a158, AC-c157c480dc72, AC-d834848b9fb1, AC-dc9c0d886a85) experienced reporting gaps during the same period.
- **TRACK-GAP / track_rate_excess** -- A 60 km disc around the area showed 3 track discontinuities during the window and none outside it, indicating a rate spike.

*Uncertainty:*

- The local discontinuity rate could not be measured outside the window, so the track evidence does not independently confirm or refute the RF findings.
- Some short deviations on RF-05:4 were observed but did not meet the event threshold.

*Alternatives:*

- The observed track gaps could be due to unrelated aircraft or system issues rather than RF interference. To support this, one would need evidence of aircraft or system faults independent of the RF environment.

*Recommended action:*

Check for independent reports of RF interference or outages in the area during the window, and review aircraft maintenance or system logs for unrelated causes of track loss.

### Hypothesis B

**Possible interference zone at RF-04, RF-05**

Stated confidence: **Medium**

FUSION-SPATIAL reports possible interference zone at RF-04, RF-05 between 2022-06-27 12:24:40 and 12:30:10 UTC, on channel(s) 4. The rule states: the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption. Behind it are 17 evidence item(s) of 4 kind(s), with 4 recorded uncertainty(ies). This account restates what the detection rules found and adds nothing to it.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- 7 findings of this kind across 2 source(s) between 12:24:50 and 12:29:40; for example, RF-04:4: power_dbm deviated by 12.30 dB at its peak.
- **FUSION-SPATIAL / possible_interference_zone** -- RF-04, RF-05: the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption.
- **TRACK-GAP / track_rate_excess** -- 60 km disc: 3 discontinuities during the window against 0 outside it, a rate ratio of 9.09.
- **TRACK-GAP / track_continuity_gap** -- 8 findings of this kind across 8 source(s) between 12:24:28 and 12:33:30; for example, AC-01df46f171f3: reporting from this aircraft broke during the window.

*Uncertainty:*

- the local discontinuity rate could not be measured: the reference period outside this window held no track findings, so the ratio would consist of nothing but the smoothing constant and is not a comparison of two observed rates. This is the majority case, and it means the aircraft side neither supports nor contradicts the radio evidence here.
- a deviation on channel 4 of RF-05 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-05 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-05 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

*Alternatives:*

- possible_sensor_fault: the deviation may be in the receivers rather than in the environment. The rule ruled this out because more than one receiver deviated together, so a common-mode failure -- a shared power supply, a shared clock, one configuration change applied to several units -- is the reading this does not exclude.
- something the rule set does not encode: these conclusions are drawn by deterministic rules that can only choose among the explanations they were written to distinguish, so an event unlike any of them is reported as whichever encoded explanation it most resembles.

*Recommended action:*

Corroborate the deviation at RF-04, RF-05 against a source outside this system -- a NOTAM, a spectrum-monitoring report, an operator log -- before treating it as interference in the environment. The aircraft side is not a clean negative here -- see the uncertainties -- so it should not be read as evidence against.

---

## Evidence pack 00264 -- 10 of 20

| | |
|---|---|
| **When** | 2022-06-27 12:44 to 12:50 |
| **Where** | RF-04, RF-05, RF-06 &middot; channel 4 |

### The conclusion being explained

> the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption.
>
> *FUSION-SPATIAL / possible_interference_zone* &middot; RF-04, RF-05, RF-06

### The evidence behind it

**RF-NOISE / rf_noise_deviation** &middot; 17 findings

power_dbm deviated by ... dB at its peak

| Source | |
|---|---|
| RF-04:4 | 13.81 &middot; 7.14 &middot; 12.52 &middot; 11.11 &middot; 9.56 &middot; 16.43 &middot; 11.43 |
| RF-05:4 | 9.51 &middot; 8.33 &middot; 13.78 &middot; 12.04 &middot; 11.53 |
| RF-06:4 | 9.82 &middot; 10.69 &middot; 13.35 &middot; 9.61 &middot; 10.16 |

**TRACK-GAP / track_rate_excess** &middot; 1 finding

**60 km disc** -- 5 discontinuities during the window against 0 outside it, a rate ratio of 15.35

**TRACK-GAP / track_continuity_gap** &middot; 18 findings

reporting from this aircraft broke during the window

AC-5642295a8c20 &middot; AC-593dc10d9de0 &middot; AC-81fef006310b &middot; AC-a7552640263d &middot; AC-a9b23027455f (x2) &middot; AC-c2503f648dd8 &middot; AC-c5ff24137199 &middot; AC-c885475688d8 &middot; AC-c91952508e7d &middot; AC-d57f79591df7 &middot; AC-d8fae9662ab2 &middot; AC-f009c216d758 &middot; AC-f65bb79d61e9 (x4) &middot; AC-f81fe1d25c0f

### What the rules could not determine

- **track** -- the local discontinuity rate could not be measured: the reference period outside this window held no track findings, so the ratio would consist of nothing but the smoothing constant and is not a comparison of two observed rates. This is the majority case, and it means the aircraft side neither supports nor contradicts the radio evidence here.
- **RF-06:4** -- (raised 3 times) a deviation on channel 4 of RF-06 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

### Hypothesis A

**Possible interference zone at RF-04, RF-05, RF-06**

Stated confidence: **Medium**

FUSION-SPATIAL reports possible interference zone at RF-04, RF-05, RF-06 between 2022-06-27 12:44:57 and 12:50:07 UTC, on channel(s) 4. The rule states: the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption. Behind it are 37 evidence item(s) of 4 kind(s), with 4 recorded uncertainty(ies). This account restates what the detection rules found and adds nothing to it.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- 17 findings of this kind across 3 source(s) between 12:45:07 and 12:49:57; for example, RF-04:4: power_dbm deviated by 13.81 dB at its peak.
- **FUSION-SPATIAL / possible_interference_zone** -- RF-04, RF-05, RF-06: the reference period holds no track findings, so its rate is nothing but the smoothing constant and the ratio compares one observed rate against an assumption. A disc with nothing in it is not a disc that showed no disruption.
- **TRACK-GAP / track_rate_excess** -- 60 km disc: 5 discontinuities during the window against 0 outside it, a rate ratio of 15.35.
- **TRACK-GAP / track_continuity_gap** -- 18 findings of this kind across 14 source(s) between 12:28:48 and 12:54:50; for example, AC-5642295a8c20: reporting from this aircraft broke during the window.

*Uncertainty:*

- the local discontinuity rate could not be measured: the reference period outside this window held no track findings, so the ratio would consist of nothing but the smoothing constant and is not a comparison of two observed rates. This is the majority case, and it means the aircraft side neither supports nor contradicts the radio evidence here.
- a deviation on channel 4 of RF-06 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-06 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-06 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

*Alternatives:*

- possible_sensor_fault: the deviation may be in the receivers rather than in the environment. The rule ruled this out because more than one receiver deviated together, so a common-mode failure -- a shared power supply, a shared clock, one configuration change applied to several units -- is the reading this does not exclude.
- something the rule set does not encode: these conclusions are drawn by deterministic rules that can only choose among the explanations they were written to distinguish, so an event unlike any of them is reported as whichever encoded explanation it most resembles.

*Recommended action:*

Corroborate the deviation at RF-04, RF-05, RF-06 against a source outside this system -- a NOTAM, a spectrum-monitoring report, an operator log -- before treating it as interference in the environment. The aircraft side is not a clean negative here -- see the uncertainties -- so it should not be read as evidence against.

### Hypothesis B

**Probable Localized RF Interference Zone Affecting Multiple Aircraft Tracks**

Stated confidence: **Medium**

During the specified window, significant and repeated RF noise deviations were observed on channel 4 across sensors RF-04, RF-05, and RF-06, coinciding with a sharp increase in aircraft track discontinuities within a 60 km area. This pattern suggests a localized interference event likely disrupted both RF monitoring and aircraft reporting.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- Multiple sensors (RF-04, RF-05, RF-06) detected substantial power_dbm deviations on channel 4, with several events exceeding 10 dB and classified as medium or high severity.
- **TRACK-GAP / track_rate_excess** -- A 60 km disc showed 5 track discontinuities during the window and none outside it, yielding a rate ratio of 15.35.
- **TRACK-GAP / track_continuity_gap** -- Several aircraft (e.g., AC-5642295a8c20, AC-593dc10d9de0, AC-81fef006310b, and others) experienced reporting gaps during the same period, indicating loss of track continuity.

*Uncertainty:*

- The local discontinuity rate outside the window could not be measured, so the aircraft track evidence does not independently confirm or contradict the RF findings.
- Some short RF deviations on RF-06:4 were observed but not called events due to duration under the 10 s minimum.

*Alternatives:*

- The observed track discontinuities could be due to unrelated aircraft or system outages rather than RF interference; this would require evidence of independent technical faults or maintenance during the window.
- Atmospheric or environmental effects could cause both RF noise and track loss, though the spatial and temporal clustering makes this less likely.

*Recommended action:*

Check for external reports of RF interference or outages in the affected area and time window, and review aircraft maintenance or system logs for independent causes of track loss.

---

## Evidence pack 00269 -- 11 of 20

| | |
|---|---|
| **When** | 2022-06-27 12:43 to 12:48 |
| **Where** | RF-07 &middot; channel 4 |

### The conclusion being explained

> one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument
>
> *SENSOR-FAULT / possible_sensor_fault* &middot; RF-07

### The evidence behind it

**RF-NOISE / rf_noise_deviation** &middot; 4 findings

power_dbm deviated by ... dB at its peak

| Source | |
|---|---|
| RF-07:4 | 11.53 &middot; 13.59 &middot; 9.68 &middot; 11.72 |

**SENSOR-FAULT / neighbour_nominal** &middot; 1 finding

**RF-06** -- RF-06 was measured and stayed within 2.0 dB of its baseline

**SENSOR-FAULT / channel_adjacency** &middot; 1 finding

**RF-07** -- the deviation is confined to 1 of 8 channels

### What the rules could not determine

- **track** -- the aircraft side was not consulted. A single-receiver fault verdict does not reach the fusion rule, so the absence of track evidence here is by design and is not a measurement that came back empty.
- **RF-07:4** -- (raised 3 times) a deviation on channel 4 of RF-07 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

### Hypothesis A

**RF-07 Channel 4 Likely Sensor Fault**

Stated confidence: **High**

The repeated, significant power deviations observed only on channel 4 of RF-07, while adjacent channels and a neighbouring receiver (RF-06) remained nominal, indicate a probable sensor fault affecting this specific channel.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- Multiple significant power_dbm deviations (up to 13.59 dB) were observed on channel 4 of RF-07 during the time window.
- **SENSOR-FAULT / neighbour_nominal** -- RF-06, a neighbouring receiver, stayed within 2.0 dB of its baseline, indicating no area-wide anomaly.
- **SENSOR-FAULT / channel_adjacency** -- The deviation was confined to 1 of 8 channels on RF-07, with adjacent channels checked and found normal.
- **SENSOR-FAULT / possible_sensor_fault** -- The system attributes the deviation to the instrument, as only one receiver deviated while its measured neighbours stayed nominal.

*Uncertainty:*

- The aircraft side was not consulted; absence of track evidence is by design and not a missing measurement.
- Some deviations on channel 4 lasted only 1 reading, under the 10 s minimum, so were observed but not called events.

*Alternatives:*

- If there were a localized external interference source affecting only channel 4 of RF-07 and not its neighbours, the observed deviations could be due to environmental RF noise rather than a sensor fault.

*Recommended action:*

Inspect and test channel 4 of RF-07 for hardware or calibration issues. If possible, corroborate with independent measurements or a portable receiver at the affected location.

### Hypothesis B

**Possible sensor fault at RF-07**

Stated confidence: **High**

SENSOR-FAULT reports possible sensor fault at RF-07 between 2022-06-27 12:43:49 and 12:48:49 UTC, on channel(s) 4. The rule states: one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument. Behind it are 7 evidence item(s) of 4 kind(s), with 4 recorded uncertainty(ies). This account restates what the detection rules found and adds nothing to it.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- 4 findings of this kind across 1 source(s) between 12:45:09 and 12:48:39; for example, RF-07:4: power_dbm deviated by 11.53 dB at its peak.
- **SENSOR-FAULT / neighbour_nominal** -- RF-06: RF-06 was measured and stayed within 2.0 dB of its baseline.
- **SENSOR-FAULT / channel_adjacency** -- RF-07: the deviation is confined to 1 of 8 channels.
- **SENSOR-FAULT / possible_sensor_fault** -- RF-07: one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument.

*Uncertainty:*

- the aircraft side was not consulted. A single-receiver fault verdict does not reach the fusion rule, so the absence of track evidence here is by design and is not a measurement that came back empty.
- a deviation on channel 4 of RF-07 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-07 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-07 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

*Alternatives:*

- possible_interference_zone: the deviation may be a real signal in the environment rather than a fault in the receiver. The rule ruled this out because the measured neighbouring receivers stayed nominal through the same window, so a neighbour that could not be measured weakens that argument.
- something the rule set does not encode: these conclusions are drawn by deterministic rules that can only choose among the explanations they were written to distinguish, so an event unlike any of them is reported as whichever encoded explanation it most resembles.

*Recommended action:*

Check the receiver at RF-07 against its own maintenance record and its neighbours' readings for the same window before treating the deviation as a signal in the environment. The aircraft side is not a clean negative here -- see the uncertainties -- so it should not be read as evidence against.

---

## Evidence pack 00273 -- 12 of 20

| | |
|---|---|
| **When** | 2022-06-27 12:38 to 12:43 |
| **Where** | RF-07 &middot; channel 4 |

### The conclusion being explained

> one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument
>
> *SENSOR-FAULT / possible_sensor_fault* &middot; RF-07

### The evidence behind it

**RF-NOISE / rf_noise_deviation** &middot; 3 findings

power_dbm deviated by ... dB at its peak

| Source | |
|---|---|
| RF-07:4 | 11.65 &middot; 8.72 &middot; 13.20 |

**SENSOR-FAULT / neighbour_nominal** &middot; 1 finding

**RF-06** -- RF-06 was measured and stayed within 2.0 dB of its baseline

**SENSOR-FAULT / channel_adjacency** &middot; 1 finding

**RF-07** -- the deviation is confined to 1 of 8 channels

### What the rules could not determine

- **track** -- the aircraft side was not consulted. A single-receiver fault verdict does not reach the fusion rule, so the absence of track evidence here is by design and is not a measurement that came back empty.

### Hypothesis A

**Possible sensor fault at RF-07**

Stated confidence: **High**

SENSOR-FAULT reports possible sensor fault at RF-07 between 2022-06-27 12:38:11 and 12:43:51 UTC, on channel(s) 4. The rule states: one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument. Behind it are 6 evidence item(s) of 4 kind(s), with 1 recorded uncertainty(ies). This account restates what the detection rules found and adds nothing to it.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- 3 findings of this kind across 1 source(s) between 12:38:41 and 12:43:31; for example, RF-07:4: power_dbm deviated by 11.65 dB at its peak.
- **SENSOR-FAULT / neighbour_nominal** -- RF-06: RF-06 was measured and stayed within 2.0 dB of its baseline.
- **SENSOR-FAULT / channel_adjacency** -- RF-07: the deviation is confined to 1 of 8 channels.
- **SENSOR-FAULT / possible_sensor_fault** -- RF-07: one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument.

*Uncertainty:*

- the aircraft side was not consulted. A single-receiver fault verdict does not reach the fusion rule, so the absence of track evidence here is by design and is not a measurement that came back empty.

*Alternatives:*

- possible_interference_zone: the deviation may be a real signal in the environment rather than a fault in the receiver. The rule ruled this out because the measured neighbouring receivers stayed nominal through the same window, so a neighbour that could not be measured weakens that argument.
- something the rule set does not encode: these conclusions are drawn by deterministic rules that can only choose among the explanations they were written to distinguish, so an event unlike any of them is reported as whichever encoded explanation it most resembles.

*Recommended action:*

Check the receiver at RF-07 against its own maintenance record and its neighbours' readings for the same window before treating the deviation as a signal in the environment. The aircraft side is not a clean negative here -- see the uncertainties -- so it should not be read as evidence against.

### Hypothesis B

**RF-07 Channel 4 Likely Sensor Fault**

Stated confidence: **High**

The observed large and repeated power deviations on RF-07 channel 4, while all other channels and neighbouring receiver RF-06 remained nominal, indicate a probable sensor fault isolated to this channel.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- RF-07 channel 4 showed significant power_dbm deviations (up to 13.20 dB) during the time window.
- **SENSOR-FAULT / neighbour_nominal** -- Neighbouring receiver RF-06 stayed within 2.0 dB of its baseline, indicating no area-wide anomaly.
- **SENSOR-FAULT / channel_adjacency** -- The deviation was confined to only 1 of 8 channels on RF-07; adjacent channels were normal.
- **SENSOR-FAULT / possible_sensor_fault** -- The pattern of one receiver deviating while its neighbours stayed nominal attributes the deviation to the instrument.

*Uncertainty:*

- The aircraft side was not consulted; absence of track evidence is by design and not a missing measurement.

*Alternatives:*

- If there were a highly localized external interference affecting only RF-07 channel 4 and not its adjacent channels or neighbouring receivers, the observed deviations could be due to an external source rather than a sensor fault.

*Recommended action:*

Physically inspect and test RF-07 channel 4 hardware for faults; if possible, compare with independent measurements or swap hardware to confirm the issue is isolated to the sensor.

---

## Evidence pack 00279 -- 13 of 20

| | |
|---|---|
| **When** | 2022-06-27 12:09 to 12:14 |
| **Where** | RF-04 &middot; channel 4 |

### The conclusion being explained

> one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument
>
> *SENSOR-FAULT / possible_sensor_fault* &middot; RF-04

### The evidence behind it

**RF-NOISE / rf_noise_deviation** &middot; 5 findings

power_dbm deviated by ... dB at its peak

| Source | |
|---|---|
| RF-04:4 | 11.58 &middot; 10.66 &middot; 10.93 &middot; 8.89 &middot; 10.60 |

**SENSOR-FAULT / neighbour_nominal** &middot; 1 finding

**RF-05** -- RF-05 was measured and stayed within 2.0 dB of its baseline

**SENSOR-FAULT / channel_adjacency** &middot; 1 finding

**RF-04** -- the deviation is confined to 1 of 8 channels

### What the rules could not determine

- **track** -- the aircraft side was not consulted. A single-receiver fault verdict does not reach the fusion rule, so the absence of track evidence here is by design and is not a measurement that came back empty.

### Hypothesis A

**Possible sensor fault at RF-04**

Stated confidence: **High**

SENSOR-FAULT reports possible sensor fault at RF-04 between 2022-06-27 12:09:46 and 12:14:56 UTC, on channel(s) 4. The rule states: one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument. Behind it are 8 evidence item(s) of 4 kind(s), with 1 recorded uncertainty(ies). This account restates what the detection rules found and adds nothing to it.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- 5 findings of this kind across 1 source(s) between 12:10:06 and 12:14:46; for example, RF-04:4: power_dbm deviated by 11.58 dB at its peak.
- **SENSOR-FAULT / neighbour_nominal** -- RF-05: RF-05 was measured and stayed within 2.0 dB of its baseline.
- **SENSOR-FAULT / channel_adjacency** -- RF-04: the deviation is confined to 1 of 8 channels.
- **SENSOR-FAULT / possible_sensor_fault** -- RF-04: one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument.

*Uncertainty:*

- the aircraft side was not consulted. A single-receiver fault verdict does not reach the fusion rule, so the absence of track evidence here is by design and is not a measurement that came back empty.

*Alternatives:*

- possible_interference_zone: the deviation may be a real signal in the environment rather than a fault in the receiver. The rule ruled this out because the measured neighbouring receivers stayed nominal through the same window, so a neighbour that could not be measured weakens that argument.
- something the rule set does not encode: these conclusions are drawn by deterministic rules that can only choose among the explanations they were written to distinguish, so an event unlike any of them is reported as whichever encoded explanation it most resembles.

*Recommended action:*

Check the receiver at RF-04 against its own maintenance record and its neighbours' readings for the same window before treating the deviation as a signal in the environment. The aircraft side is not a clean negative here -- see the uncertainties -- so it should not be read as evidence against.

### Hypothesis B

**RF-04 Channel 4 Likely Sensor Fault**

Stated confidence: **High**

The observed large power deviations on RF-04 channel 4 are likely due to a sensor fault, as the anomaly is confined to a single channel and neighbouring sensors and channels remained nominal.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- Multiple significant power_dbm deviations (up to 11.58 dB) were observed on RF-04 channel 4 during the time window.
- **SENSOR-FAULT / neighbour_nominal** -- Neighbouring sensor RF-05 stayed within 2.0 dB of its baseline, indicating no area-wide anomaly.
- **SENSOR-FAULT / channel_adjacency** -- The deviation was confined to 1 of 8 channels on RF-04; adjacent channels were normal.
- **SENSOR-FAULT / possible_sensor_fault** -- The pattern of one receiver deviating while its measured neighbours stayed nominal attributes the deviation to the instrument.

*Uncertainty:*

- The aircraft side was not consulted. A single-receiver fault verdict does not reach the fusion rule, so the absence of track evidence here is by design and is not a measurement that came back empty.

*Alternatives:*

- If there were a highly localized external interference affecting only RF-04 channel 4 and not its neighbours, this could also explain the deviation, but the evidence favours an internal sensor fault.

*Recommended action:*

Physically inspect and test RF-04 channel 4 hardware to confirm or rule out a sensor fault; compare with independent measurements if available.

---

## Evidence pack 00280 -- 14 of 20

| | |
|---|---|
| **When** | 2022-06-27 12:09 to 12:14 |
| **Where** | RF-06 &middot; channel 4 |

### The conclusion being explained

> one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument
>
> *SENSOR-FAULT / possible_sensor_fault* &middot; RF-06

### The evidence behind it

**RF-NOISE / rf_noise_deviation** &middot; 4 findings

power_dbm deviated by ... dB at its peak

| Source | |
|---|---|
| RF-06:4 | 8.66 &middot; 13.42 &middot; 8.40 &middot; 10.68 |

**SENSOR-FAULT / neighbour_nominal** &middot; 2 findings

... was measured and stayed within 2.0 dB of its baseline

| Source | |
|---|---|
| RF-07 | RF-07 |
| RF-05 | RF-05 |

**SENSOR-FAULT / channel_adjacency** &middot; 1 finding

**RF-06** -- the deviation is confined to 1 of 8 channels

### What the rules could not determine

- **track** -- the aircraft side was not consulted. A single-receiver fault verdict does not reach the fusion rule, so the absence of track evidence here is by design and is not a measurement that came back empty.
- **RF-06:4** -- (raised 3 times) a deviation on channel 4 of RF-06 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

### Hypothesis A

**RF-06 Channel 4 Likely Sensor Fault**

Stated confidence: **High**

The repeated, significant power deviations on channel 4 of RF-06, while adjacent channels and neighbouring receivers remained nominal, indicate a probable sensor fault confined to this channel.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- Multiple observed power_dbm deviations (8.66 dB, 13.42 dB, 8.40 dB, 10.68 dB) occurred on channel 4 of RF-06 during the time window.
- **SENSOR-FAULT / neighbour_nominal** -- Neighbouring receivers RF-05 and RF-07 stayed within 2.0 dB of their baselines, showing no similar deviations.
- **SENSOR-FAULT / channel_adjacency** -- The deviation was confined to 1 of 8 channels on RF-06; adjacent channels were checked and found normal.
- **SENSOR-FAULT / possible_sensor_fault** -- The system attributes the deviation to the instrument, as only one receiver deviated while its neighbours stayed nominal.

*Uncertainty:*

- The aircraft side was not consulted; absence of track evidence is by design and not a missing measurement.
- Some deviations on channel 4 of RF-06 lasted only 1 reading, under the 10 s minimum, so were observed but not called events.

*Alternatives:*

- If there were a localized external interference affecting only channel 4 of RF-06 and not its neighbours or adjacent channels, this could explain the deviation, but the evidence strongly favours an internal sensor fault.

*Recommended action:*

Physically inspect and test channel 4 of RF-06 for hardware or calibration faults; compare with independent measurement equipment if available.

### Hypothesis B

**Possible sensor fault at RF-06**

Stated confidence: **High**

SENSOR-FAULT reports possible sensor fault at RF-06 between 2022-06-27 12:09:47 and 12:14:47 UTC, on channel(s) 4. The rule states: one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument. Behind it are 8 evidence item(s) of 4 kind(s), with 4 recorded uncertainty(ies). This account restates what the detection rules found and adds nothing to it.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- 4 findings of this kind across 1 source(s) between 12:10:57 and 12:14:37; for example, RF-06:4: power_dbm deviated by 8.66 dB at its peak.
- **SENSOR-FAULT / neighbour_nominal** -- 2 findings of this kind across 2 source(s) between 12:09:47 and 12:14:47; for example, RF-07: RF-07 was measured and stayed within 2.0 dB of its baseline.
- **SENSOR-FAULT / channel_adjacency** -- RF-06: the deviation is confined to 1 of 8 channels.
- **SENSOR-FAULT / possible_sensor_fault** -- RF-06: one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument.

*Uncertainty:*

- the aircraft side was not consulted. A single-receiver fault verdict does not reach the fusion rule, so the absence of track evidence here is by design and is not a measurement that came back empty.
- a deviation on channel 4 of RF-06 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-06 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-06 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

*Alternatives:*

- possible_interference_zone: the deviation may be a real signal in the environment rather than a fault in the receiver. The rule ruled this out because the measured neighbouring receivers stayed nominal through the same window, so a neighbour that could not be measured weakens that argument.
- something the rule set does not encode: these conclusions are drawn by deterministic rules that can only choose among the explanations they were written to distinguish, so an event unlike any of them is reported as whichever encoded explanation it most resembles.

*Recommended action:*

Check the receiver at RF-06 against its own maintenance record and its neighbours' readings for the same window before treating the deviation as a signal in the environment. The aircraft side is not a clean negative here -- see the uncertainties -- so it should not be read as evidence against.

---

## Evidence pack 00284 -- 15 of 20

| | |
|---|---|
| **When** | 2022-06-27 12:26 to 12:30 |
| **Where** | RF-02 &middot; channel 4 |

### The conclusion being explained

> one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument
>
> *SENSOR-FAULT / possible_sensor_fault* &middot; RF-02

### The evidence behind it

**RF-NOISE / rf_noise_deviation** &middot; 2 findings

power_dbm deviated by ... dB at its peak

| Source | |
|---|---|
| RF-02:4 | 10.11 &middot; 10.04 |

**SENSOR-FAULT / neighbour_nominal** &middot; 1 finding

**RF-01** -- RF-01 was measured and stayed within 2.0 dB of its baseline

**SENSOR-FAULT / channel_adjacency** &middot; 1 finding

**RF-02** -- the deviation is confined to 1 of 8 channels

### What the rules could not determine

- **track** -- the aircraft side was not consulted. A single-receiver fault verdict does not reach the fusion rule, so the absence of track evidence here is by design and is not a measurement that came back empty.
- **RF-02:4** -- (raised 3 times) a deviation on channel 4 of RF-02 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

### Hypothesis A

**RF-02 Channel 4 Likely Sensor Fault**

Stated confidence: **High**

The observed power deviations on channel 4 of RF-02 are likely due to a sensor fault, as the anomaly is confined to a single channel, neighbouring channels and nearby receiver RF-01 remained nominal, and the deviation is attributed to the instrument itself.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- Channel 4 of RF-02 showed power_dbm deviations exceeding 10 dB at two separate intervals.
- **SENSOR-FAULT / neighbour_nominal** -- RF-01, a neighbouring receiver, stayed within 2.0 dB of its baseline during the same period.
- **SENSOR-FAULT / channel_adjacency** -- The deviation was confined to only 1 of 8 channels on RF-02; adjacent channels were normal.
- **SENSOR-FAULT / possible_sensor_fault** -- The deviation is attributed to the instrument, as only one receiver deviated while its measured neighbours stayed nominal.

*Uncertainty:*

- The aircraft side was not consulted; absence of track evidence is by design and not a missing measurement.
- Some deviations on channel 4 of RF-02 lasted only 1 reading, under the 10 s minimum, so were observed but not called events.

*Alternatives:*

- If there were a strong, highly localized external interference affecting only channel 4 of RF-02 and not its neighbours, the observed deviation could be due to an external source rather than a sensor fault.

*Recommended action:*

Physically inspect and test RF-02, especially channel 4, to confirm sensor health and rule out hardware or calibration issues.

### Hypothesis B

**Possible sensor fault at RF-02**

Stated confidence: **High**

SENSOR-FAULT reports possible sensor fault at RF-02 between 2022-06-27 12:26:55 and 12:30:15 UTC, on channel(s) 4. The rule states: one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument. Behind it are 5 evidence item(s) of 4 kind(s), with 4 recorded uncertainty(ies). This account restates what the detection rules found and adds nothing to it.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- 2 findings of this kind across 1 source(s) between 12:26:55 and 12:29:25; for example, RF-02:4: power_dbm deviated by 10.11 dB at its peak.
- **SENSOR-FAULT / neighbour_nominal** -- RF-01: RF-01 was measured and stayed within 2.0 dB of its baseline.
- **SENSOR-FAULT / channel_adjacency** -- RF-02: the deviation is confined to 1 of 8 channels.
- **SENSOR-FAULT / possible_sensor_fault** -- RF-02: one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument.

*Uncertainty:*

- the aircraft side was not consulted. A single-receiver fault verdict does not reach the fusion rule, so the absence of track evidence here is by design and is not a measurement that came back empty.
- a deviation on channel 4 of RF-02 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-02 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-02 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

*Alternatives:*

- possible_interference_zone: the deviation may be a real signal in the environment rather than a fault in the receiver. The rule ruled this out because the measured neighbouring receivers stayed nominal through the same window, so a neighbour that could not be measured weakens that argument.
- something the rule set does not encode: these conclusions are drawn by deterministic rules that can only choose among the explanations they were written to distinguish, so an event unlike any of them is reported as whichever encoded explanation it most resembles.

*Recommended action:*

Check the receiver at RF-02 against its own maintenance record and its neighbours' readings for the same window before treating the deviation as a signal in the environment. The aircraft side is not a clean negative here -- see the uncertainties -- so it should not be read as evidence against.

---

## Evidence pack 00288 -- 16 of 20

| | |
|---|---|
| **When** | 2022-06-27 12:25 to 12:30 |
| **Where** | RF-02 &middot; channel 4 |

### The conclusion being explained

> one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument
>
> *SENSOR-FAULT / possible_sensor_fault* &middot; RF-02

### The evidence behind it

**RF-NOISE / rf_noise_deviation** &middot; 6 findings

power_dbm deviated by ... dB at its peak

| Source | |
|---|---|
| RF-02:4 | 10.73 &middot; 10.40 &middot; 11.28 &middot; 9.93 &middot; 11.07 &middot; 10.53 |

**SENSOR-FAULT / neighbour_nominal** &middot; 1 finding

**RF-01** -- RF-01 was measured and stayed within 2.0 dB of its baseline

**SENSOR-FAULT / channel_adjacency** &middot; 1 finding

**RF-02** -- the deviation is confined to 1 of 8 channels

### What the rules could not determine

- **track** -- the aircraft side was not consulted. A single-receiver fault verdict does not reach the fusion rule, so the absence of track evidence here is by design and is not a measurement that came back empty.
- **RF-02:4** -- a deviation on channel 4 of RF-02 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

### Hypothesis A

**Possible sensor fault at RF-02**

Stated confidence: **High**

SENSOR-FAULT reports possible sensor fault at RF-02 between 2022-06-27 12:25:33 and 12:30:53 UTC, on channel(s) 4. The rule states: one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument. Behind it are 9 evidence item(s) of 4 kind(s), with 2 recorded uncertainty(ies). This account restates what the detection rules found and adds nothing to it.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- 6 findings of this kind across 1 source(s) between 12:25:33 and 12:30:23; for example, RF-02:4: power_dbm deviated by 10.73 dB at its peak.
- **SENSOR-FAULT / neighbour_nominal** -- RF-01: RF-01 was measured and stayed within 2.0 dB of its baseline.
- **SENSOR-FAULT / channel_adjacency** -- RF-02: the deviation is confined to 1 of 8 channels.
- **SENSOR-FAULT / possible_sensor_fault** -- RF-02: one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument.

*Uncertainty:*

- the aircraft side was not consulted. A single-receiver fault verdict does not reach the fusion rule, so the absence of track evidence here is by design and is not a measurement that came back empty.
- a deviation on channel 4 of RF-02 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

*Alternatives:*

- possible_interference_zone: the deviation may be a real signal in the environment rather than a fault in the receiver. The rule ruled this out because the measured neighbouring receivers stayed nominal through the same window, so a neighbour that could not be measured weakens that argument.
- something the rule set does not encode: these conclusions are drawn by deterministic rules that can only choose among the explanations they were written to distinguish, so an event unlike any of them is reported as whichever encoded explanation it most resembles.

*Recommended action:*

Check the receiver at RF-02 against its own maintenance record and its neighbours' readings for the same window before treating the deviation as a signal in the environment. The aircraft side is not a clean negative here -- see the uncertainties -- so it should not be read as evidence against.

### Hypothesis B

**RF-02 Channel 4 Likely Sensor Fault**

Stated confidence: **High**

The repeated, significant power deviations observed only on channel 4 of RF-02, while all other channels and neighbouring receivers remained nominal, strongly indicate a sensor fault isolated to this channel.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- Multiple observed power_dbm deviations between 9.93 and 11.28 dB occurred on channel 4 of RF-02 during the time window.
- **SENSOR-FAULT / neighbour_nominal** -- RF-01, a neighbouring receiver, stayed within 2.0 dB of its baseline throughout the period.
- **SENSOR-FAULT / channel_adjacency** -- The deviation was confined to 1 of 8 channels on RF-02, with adjacent channels checked and found nominal.
- **SENSOR-FAULT / possible_sensor_fault** -- The system attributes the deviation to the instrument, as only one receiver deviated while its measured neighbours stayed nominal.

*Uncertainty:*

- The aircraft side was not consulted; absence of track evidence is by design and not a missing measurement.
- A deviation on channel 4 of RF-02 lasted only 1 reading, under the 10 s minimum, so it was observed but not called an event.

*Alternatives:*

- If there were a strong, highly localized external RF interference affecting only channel 4 of RF-02 and not its neighbours or adjacent channels, this could explain the deviation, but the evidence does not support this scenario.

*Recommended action:*

Inspect and test channel 4 hardware on RF-02 for faults; if possible, corroborate with independent sensor diagnostics or maintenance logs.

---

## Evidence pack 00289 -- 17 of 20

| | |
|---|---|
| **When** | 2022-06-27 12:31 to 12:36 |
| **Where** | RF-07 &middot; channel 4 |

### The conclusion being explained

> one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument
>
> *SENSOR-FAULT / possible_sensor_fault* &middot; RF-07

### The evidence behind it

**RF-NOISE / rf_noise_deviation** &middot; 4 findings

power_dbm deviated by ... dB at its peak

| Source | |
|---|---|
| RF-07:4 | 8.51 &middot; 11.63 &middot; 10.91 &middot; 12.76 |

**SENSOR-FAULT / neighbour_nominal** &middot; 1 finding

**RF-06** -- RF-06 was measured and stayed within 2.0 dB of its baseline

**SENSOR-FAULT / channel_adjacency** &middot; 1 finding

**RF-07** -- the deviation is confined to 1 of 8 channels

### What the rules could not determine

- **track** -- the aircraft side was not consulted. A single-receiver fault verdict does not reach the fusion rule, so the absence of track evidence here is by design and is not a measurement that came back empty.
- **RF-07:4** -- (raised 3 times) a deviation on channel 4 of RF-07 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

### Hypothesis A

**Possible sensor fault at RF-07**

Stated confidence: **High**

SENSOR-FAULT reports possible sensor fault at RF-07 between 2022-06-27 12:31:32 and 12:36:22 UTC, on channel(s) 4. The rule states: one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument. Behind it are 7 evidence item(s) of 4 kind(s), with 4 recorded uncertainty(ies). This account restates what the detection rules found and adds nothing to it.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- 4 findings of this kind across 1 source(s) between 12:31:32 and 12:36:22; for example, RF-07:4: power_dbm deviated by 8.51 dB at its peak.
- **SENSOR-FAULT / neighbour_nominal** -- RF-06: RF-06 was measured and stayed within 2.0 dB of its baseline.
- **SENSOR-FAULT / channel_adjacency** -- RF-07: the deviation is confined to 1 of 8 channels.
- **SENSOR-FAULT / possible_sensor_fault** -- RF-07: one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument.

*Uncertainty:*

- the aircraft side was not consulted. A single-receiver fault verdict does not reach the fusion rule, so the absence of track evidence here is by design and is not a measurement that came back empty.
- a deviation on channel 4 of RF-07 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-07 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-07 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

*Alternatives:*

- possible_interference_zone: the deviation may be a real signal in the environment rather than a fault in the receiver. The rule ruled this out because the measured neighbouring receivers stayed nominal through the same window, so a neighbour that could not be measured weakens that argument.
- something the rule set does not encode: these conclusions are drawn by deterministic rules that can only choose among the explanations they were written to distinguish, so an event unlike any of them is reported as whichever encoded explanation it most resembles.

*Recommended action:*

Check the receiver at RF-07 against its own maintenance record and its neighbours' readings for the same window before treating the deviation as a signal in the environment. The aircraft side is not a clean negative here -- see the uncertainties -- so it should not be read as evidence against.

### Hypothesis B

**RF-07 Channel 4 Likely Sensor Fault**

Stated confidence: **High**

The repeated, significant power deviations observed only on channel 4 of RF-07, while all other channels and neighbouring receiver RF-06 remained nominal, strongly suggest a sensor fault isolated to this channel.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- Multiple significant power_dbm deviations (8.51–12.76 dB) were observed on channel 4 of RF-07 during the time window.
- **SENSOR-FAULT / neighbour_nominal** -- Neighbouring receiver RF-06 stayed within 2.0 dB of its baseline throughout the period.
- **SENSOR-FAULT / channel_adjacency** -- The deviation was confined to 1 of 8 channels on RF-07; adjacent channels were checked and found nominal.
- **SENSOR-FAULT / possible_sensor_fault** -- The system attributes the deviation to the instrument, as only one receiver deviated while its measured neighbours stayed nominal.

*Uncertainty:*

- The aircraft side was not consulted; absence of track evidence is by design and not a missing measurement.
- Some deviations on channel 4 lasted only 1 reading and were not called events, but these were observed and not ignored.

*Alternatives:*

- An external, highly localized RF interference source could cause similar deviations, but this is unlikely given the lack of effect on adjacent channels and neighbouring receivers.

*Recommended action:*

Physically inspect and test RF-07 channel 4 hardware for faults; if possible, compare with independent sensor data from the same area and time.

---

## Evidence pack 00295 -- 18 of 20

| | |
|---|---|
| **When** | 2022-06-27 12:23 to 12:28 |
| **Where** | RF-01 &middot; channel 4 |

### The conclusion being explained

> one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument
>
> *SENSOR-FAULT / possible_sensor_fault* &middot; RF-01

### The evidence behind it

**RF-NOISE / rf_noise_deviation** &middot; 7 findings

power_dbm deviated by ... dB at its peak

| Source | |
|---|---|
| RF-01:4 | 10.62 &middot; 9.16 &middot; 8.73 &middot; 14.11 &middot; 8.60 &middot; 10.51 &middot; 9.27 |

**SENSOR-FAULT / neighbour_nominal** &middot; 2 findings

... was measured and stayed within 2.0 dB of its baseline

| Source | |
|---|---|
| RF-02 | RF-02 |
| RF-03 | RF-03 |

**SENSOR-FAULT / channel_adjacency** &middot; 1 finding

**RF-01** -- the deviation is confined to 1 of 8 channels

### What the rules could not determine

- **track** -- the aircraft side was not consulted. A single-receiver fault verdict does not reach the fusion rule, so the absence of track evidence here is by design and is not a measurement that came back empty.
- **RF-01:4** -- a deviation on channel 4 of RF-01 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

### Hypothesis A

**Possible sensor fault at RF-01**

Stated confidence: **High**

SENSOR-FAULT reports possible sensor fault at RF-01 between 2022-06-27 12:23:19 and 12:28:59 UTC, on channel(s) 4. The rule states: one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument. Behind it are 11 evidence item(s) of 4 kind(s), with 2 recorded uncertainty(ies). This account restates what the detection rules found and adds nothing to it.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- 7 findings of this kind across 1 source(s) between 12:23:49 and 12:28:09; for example, RF-01:4: power_dbm deviated by 10.62 dB at its peak.
- **SENSOR-FAULT / neighbour_nominal** -- 2 findings of this kind across 2 source(s) between 12:23:19 and 12:28:59; for example, RF-02: RF-02 was measured and stayed within 2.0 dB of its baseline.
- **SENSOR-FAULT / channel_adjacency** -- RF-01: the deviation is confined to 1 of 8 channels.
- **SENSOR-FAULT / possible_sensor_fault** -- RF-01: one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument.

*Uncertainty:*

- the aircraft side was not consulted. A single-receiver fault verdict does not reach the fusion rule, so the absence of track evidence here is by design and is not a measurement that came back empty.
- a deviation on channel 4 of RF-01 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

*Alternatives:*

- possible_interference_zone: the deviation may be a real signal in the environment rather than a fault in the receiver. The rule ruled this out because the measured neighbouring receivers stayed nominal through the same window, so a neighbour that could not be measured weakens that argument.
- something the rule set does not encode: these conclusions are drawn by deterministic rules that can only choose among the explanations they were written to distinguish, so an event unlike any of them is reported as whichever encoded explanation it most resembles.

*Recommended action:*

Check the receiver at RF-01 against its own maintenance record and its neighbours' readings for the same window before treating the deviation as a signal in the environment. The aircraft side is not a clean negative here -- see the uncertainties -- so it should not be read as evidence against.

### Hypothesis B

**RF-01 Channel 4 Likely Sensor Fault**

Stated confidence: **High**

The repeated, significant power deviations observed only on channel 4 of RF-01, while adjacent channels and neighbouring receivers remained nominal, indicate a likely sensor fault confined to this channel.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- Multiple findings show power_dbm deviations between 8.60 dB and 14.11 dB at their peaks on channel 4 of RF-01.
- **SENSOR-FAULT / neighbour_nominal** -- RF-02 and RF-03, measured over the same period, stayed within 2.0 dB of their baselines, indicating no area-wide anomaly.
- **SENSOR-FAULT / channel_adjacency** -- The deviation is confined to 1 of 8 channels on RF-01; adjacent channels 3 and 5 were checked and found normal.
- **SENSOR-FAULT / possible_sensor_fault** -- One receiver deviated while its measured neighbours stayed nominal, attributing the deviation to the instrument.

*Uncertainty:*

- The aircraft side was not consulted. A single-receiver fault verdict does not reach the fusion rule, so the absence of track evidence here is by design and is not a measurement that came back empty.
- A deviation on channel 4 of RF-01 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

*Alternatives:*

- If there were a localized external interference source affecting only channel 4 of RF-01 and not its neighbours or adjacent channels, this could explain the deviation, but the evidence does not support this scenario.

*Recommended action:*

Physically inspect and test channel 4 of RF-01 for hardware or calibration faults; compare with independent measurements or a portable test source at the site.

---

## Evidence pack 00299 -- 19 of 20

| | |
|---|---|
| **When** | 2022-06-27 12:09 to 12:13 |
| **Where** | RF-06 &middot; channel 4 |

### The conclusion being explained

> one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument
>
> *SENSOR-FAULT / possible_sensor_fault* &middot; RF-06

### The evidence behind it

**RF-NOISE / rf_noise_deviation** &middot; 2 findings

power_dbm deviated by ... dB at its peak

| Source | |
|---|---|
| RF-06:4 | 12.24 &middot; 15.17 |

**SENSOR-FAULT / neighbour_nominal** &middot; 2 findings

... was measured and stayed within 2.0 dB of its baseline

| Source | |
|---|---|
| RF-07 | RF-07 |
| RF-05 | RF-05 |

**SENSOR-FAULT / channel_adjacency** &middot; 1 finding

**RF-06** -- the deviation is confined to 1 of 8 channels

### What the rules could not determine

- **track** -- the aircraft side was not consulted. A single-receiver fault verdict does not reach the fusion rule, so the absence of track evidence here is by design and is not a measurement that came back empty.
- **RF-06:4** -- (raised 2 times) a deviation on channel 4 of RF-06 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

### Hypothesis A

**Possible sensor fault at RF-06**

Stated confidence: **High**

SENSOR-FAULT reports possible sensor fault at RF-06 between 2022-06-27 12:09:01 and 12:13:51 UTC, on channel(s) 4. The rule states: one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument. Behind it are 6 evidence item(s) of 4 kind(s), with 3 recorded uncertainty(ies). This account restates what the detection rules found and adds nothing to it.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- 2 findings of this kind across 1 source(s) between 12:10:01 and 12:13:51; for example, RF-06:4: power_dbm deviated by 12.24 dB at its peak.
- **SENSOR-FAULT / neighbour_nominal** -- 2 findings of this kind across 2 source(s) between 12:09:01 and 12:13:51; for example, RF-07: RF-07 was measured and stayed within 2.0 dB of its baseline.
- **SENSOR-FAULT / channel_adjacency** -- RF-06: the deviation is confined to 1 of 8 channels.
- **SENSOR-FAULT / possible_sensor_fault** -- RF-06: one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument.

*Uncertainty:*

- the aircraft side was not consulted. A single-receiver fault verdict does not reach the fusion rule, so the absence of track evidence here is by design and is not a measurement that came back empty.
- a deviation on channel 4 of RF-06 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.
- a deviation on channel 4 of RF-06 lasted 1 reading(s), under the 10 s minimum, so it was observed and not called an event.

*Alternatives:*

- possible_interference_zone: the deviation may be a real signal in the environment rather than a fault in the receiver. The rule ruled this out because the measured neighbouring receivers stayed nominal through the same window, so a neighbour that could not be measured weakens that argument.
- something the rule set does not encode: these conclusions are drawn by deterministic rules that can only choose among the explanations they were written to distinguish, so an event unlike any of them is reported as whichever encoded explanation it most resembles.

*Recommended action:*

Check the receiver at RF-06 against its own maintenance record and its neighbours' readings for the same window before treating the deviation as a signal in the environment. The aircraft side is not a clean negative here -- see the uncertainties -- so it should not be read as evidence against.

### Hypothesis B

**RF-06 Channel 4 Power Deviation Likely Due to Sensor Fault**

Stated confidence: **High**

Significant power deviations were observed on channel 4 of RF-06, while adjacent channels and neighbouring receivers remained nominal, indicating the anomaly is likely due to a fault in the RF-06 sensor rather than an external RF event.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- Channel 4 of RF-06 showed power_dbm deviations peaking at 12.24 dB and 15.17 dB during the alert window.
- **SENSOR-FAULT / neighbour_nominal** -- Neighbouring receivers RF-05 and RF-07 stayed within 2.0 dB of their baselines during the same period.
- **SENSOR-FAULT / channel_adjacency** -- The deviation was confined to only 1 of 8 channels on RF-06, with adjacent channels 3 and 5 remaining normal.
- **SENSOR-FAULT / possible_sensor_fault** -- The system attributes the deviation to the instrument, as only one receiver deviated while its measured neighbours stayed nominal.

*Uncertainty:*

- The aircraft side was not consulted; absence of track evidence is by design and not a missing measurement.
- Short deviations on channel 4 of RF-06 lasting under 10 seconds were observed but not called events.

*Alternatives:*

- A rare, highly localized external RF event could have affected only channel 4 of RF-06 without impacting adjacent channels or neighbouring receivers, but this is unlikely given the evidence.

*Recommended action:*

Inspect and test RF-06, especially channel 4, for hardware or calibration faults. Cross-check with independent sensor logs or field diagnostics to confirm the anomaly is not environmental.

---

## Evidence pack 00302 -- 20 of 20

| | |
|---|---|
| **When** | 2022-06-27 12:37 to 12:42 |
| **Where** | RF-05 &middot; channel 4 |

### The conclusion being explained

> one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument
>
> *SENSOR-FAULT / possible_sensor_fault* &middot; RF-05

### The evidence behind it

**RF-NOISE / rf_noise_deviation** &middot; 4 findings

power_dbm deviated by ... dB at its peak

| Source | |
|---|---|
| RF-05:4 | 13.28 &middot; 13.36 &middot; 11.97 &middot; 10.90 |

**SENSOR-FAULT / neighbour_nominal** &middot; 2 findings

... was measured and stayed within 2.0 dB of its baseline

| Source | |
|---|---|
| RF-06 | RF-06 |
| RF-04 | RF-04 |

**SENSOR-FAULT / channel_adjacency** &middot; 1 finding

**RF-05** -- the deviation is confined to 1 of 8 channels

### What the rules could not determine

- **track** -- the aircraft side was not consulted. A single-receiver fault verdict does not reach the fusion rule, so the absence of track evidence here is by design and is not a measurement that came back empty.

### Hypothesis A

**Possible sensor fault at RF-05**

Stated confidence: **High**

SENSOR-FAULT reports possible sensor fault at RF-05 between 2022-06-27 12:37:17 and 12:42:07 UTC, on channel(s) 4. The rule states: one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument. Behind it are 8 evidence item(s) of 4 kind(s), with 1 recorded uncertainty(ies). This account restates what the detection rules found and adds nothing to it.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- 4 findings of this kind across 1 source(s) between 12:37:17 and 12:42:07; for example, RF-05:4: power_dbm deviated by 13.28 dB at its peak.
- **SENSOR-FAULT / neighbour_nominal** -- 2 findings of this kind across 2 source(s) between 12:37:17 and 12:42:07; for example, RF-06: RF-06 was measured and stayed within 2.0 dB of its baseline.
- **SENSOR-FAULT / channel_adjacency** -- RF-05: the deviation is confined to 1 of 8 channels.
- **SENSOR-FAULT / possible_sensor_fault** -- RF-05: one receiver deviated while its measured neighbours stayed nominal, which attributes the deviation to the instrument.

*Uncertainty:*

- the aircraft side was not consulted. A single-receiver fault verdict does not reach the fusion rule, so the absence of track evidence here is by design and is not a measurement that came back empty.

*Alternatives:*

- possible_interference_zone: the deviation may be a real signal in the environment rather than a fault in the receiver. The rule ruled this out because the measured neighbouring receivers stayed nominal through the same window, so a neighbour that could not be measured weakens that argument.
- something the rule set does not encode: these conclusions are drawn by deterministic rules that can only choose among the explanations they were written to distinguish, so an event unlike any of them is reported as whichever encoded explanation it most resembles.

*Recommended action:*

Check the receiver at RF-05 against its own maintenance record and its neighbours' readings for the same window before treating the deviation as a signal in the environment. The aircraft side is not a clean negative here -- see the uncertainties -- so it should not be read as evidence against.

### Hypothesis B

**RF-05 Channel 4 Power Deviation Likely Due to Sensor Fault**

Stated confidence: **High**

The persistent and significant power deviations observed only on channel 4 of RF-05, while adjacent channels and neighbouring receivers RF-04 and RF-06 remained nominal, strongly indicate a sensor fault localized to RF-05 channel 4.

*Supporting evidence:*

- **RF-NOISE / rf_noise_deviation** -- RF-05 channel 4 showed repeated power_dbm deviations between 10.90 and 13.36 dB during the time window.
- **SENSOR-FAULT / neighbour_nominal** -- Neighbouring receivers RF-04 and RF-06 stayed within 2.0 dB of their baselines, indicating no area-wide anomaly.
- **SENSOR-FAULT / channel_adjacency** -- The deviation was confined to only 1 of 8 channels on RF-05, with adjacent channels normal.
- **SENSOR-FAULT / possible_sensor_fault** -- The system attributes the deviation to the instrument, as only one receiver deviated while its neighbours stayed nominal.

*Uncertainty:*

- The aircraft side was not consulted. The absence of track evidence is by design and not a missing measurement.

*Alternatives:*

- A rare, highly localized external interference affecting only RF-05 channel 4 could produce similar symptoms, but would require confirmation that no external source was present during the event.

*Recommended action:*

Physically inspect RF-05 channel 4 hardware and review its calibration and maintenance records. If possible, cross-check with independent sensors or logs to rule out external interference.
