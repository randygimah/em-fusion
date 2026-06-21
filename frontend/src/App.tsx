import operationalPicture from "./mocks/operationalPictureMock";
import OperationalPictureScreen from "./screens/operationalPicture";

const App = () => {
  return <OperationalPictureScreen operationalPicture={operationalPicture} />;
};
export default App;
