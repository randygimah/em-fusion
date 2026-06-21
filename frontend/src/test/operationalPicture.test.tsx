import { describe, it, beforeEach, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import operationalPicture from "../mocks/operationalPictureMock";
import OperationalPictureScreen from "../screens/operationalPicture";

describe("OperationalPictureScreen", () => {
  beforeEach(() => {
    render(<OperationalPictureScreen operationalPicture={operationalPicture} />);
  });
  it("renders the operational picture screen with correct data", () => {
    expect(screen.getByText(operationalPicture.rfSensors[0].stationName)).toBeInTheDocument();
  });
});
