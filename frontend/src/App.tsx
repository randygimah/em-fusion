import { useOperationalPicture } from "./hooks/useOperationalPicture";
import OperationalPictureScreen from "./screens/operationalPicture";

// The seam. This is the only place that knows the picture is fetched rather
// than passed in, which is what the contract-first structure was for: the
// screen still takes a typed value and no component changed when the mock
// stopped being the source (spec: api-003).
const App = () => {
  const { picture, degraded } = useOperationalPicture();

  return <OperationalPictureScreen operationalPicture={picture} degraded={degraded} />;
};
export default App;
