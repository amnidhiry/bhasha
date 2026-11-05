import { render } from "preact";
import { useCallback, useEffect, useState } from "preact/hooks";
import { api } from "./api";
import { TabBar } from "./components/TabBar";
import { ToastHost } from "./components/Toast";
import { flush } from "./outbox";
import { useRoute } from "./router";
import { Library } from "./views/Library";
import { Progress } from "./views/Progress";
import { Reader } from "./views/Reader";
import { Review } from "./views/Review";
import { Drill, Sounds } from "./views/Sounds";
import { Journal } from "./views/Journal";
import "./styles.css";

function App() {
  const route = useRoute();
  const [due, setDue] = useState(0);
  const refreshDue = useCallback(() => {
    void flush().then(() => api.due().then((d) => setDue(d.length)).catch(() => {}));
  }, []);
  useEffect(refreshDue, [refreshDue, route.name]);

  return (
    <>
      {route.name === "library" && <Library />}
      {route.name === "read" && <Reader id={route.id} onReviewsChanged={refreshDue} />}
      {route.name === "review" && <Review onCount={setDue} />}
      {route.name === "progress" && <Progress />}
      {route.name === "sounds" && <Sounds />}
      {route.name === "journal" && <Journal />}
      {route.name === "drill" && <Drill key={route.drill} drill={route.drill} />}
      <TabBar route={route} due={due} />
      <ToastHost />
    </>
  );
}

render(<App />, document.getElementById("app")!);

// Service workers need a secure context (HTTPS, or localhost).
if ("serviceWorker" in navigator && window.isSecureContext && import.meta.env.PROD) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
