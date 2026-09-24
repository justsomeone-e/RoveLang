importScripts('evaluator.js?v=5.0.3-studio-1');
self.onmessage = ({ data }) => {
  try {
    self.postMessage(RovePreview.evaluateRove(data));
  } catch (error) {
    self.postMessage({ output: [], error: error.message });
  }
};
