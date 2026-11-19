// Minimal benchmark wrapper for the Milestone 2C.0 SwingPoc.
// It auto-starts so startup timing is comparable with the SwingJS artifact.
(async () => {
  try {
    const initStarted = performance.now();
    await cheerpjInit({ version: 8, status: "none" });
    document.body.dataset.initMs = String(Math.round(performance.now() - initStarted));
    cheerpjCreateDisplay(720, 540, document.getElementById("display"));
    document.body.dataset.status = "running";
    const exitCode = await cheerpjRunMain("poc.SwingPoc", "/app/SwingPoc.jar");
    document.body.dataset.status = "exited";
    document.body.dataset.exitCode = String(exitCode);
  } catch (error) {
    document.body.dataset.status = "error";
    document.body.dataset.error = String((error && error.stack) || error);
    console.error("BENCHMARK_ERROR", error);
  }
})();
