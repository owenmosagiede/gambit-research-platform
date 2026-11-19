"use strict";

// Static documentation only. This module deliberately has no network access.
(() => {
  const $ = id => document.getElementById(id);
  const feature = $("feature"), scope = $("scope"), target = $("target"), example = $("contract-example");
  if (!feature || !scope || !target || !example) return;
  const features = [
    "FEATURE_RECIPE_556e0cd681bb5a4db09034ea5d3e50826ce4c9925536a70c8d8c9cef739e5b5c",
    "FEATURE_RECIPE_e79063e3de1bf94bb82c5cb5e276841abb70655eeadfda47e8851562205a90f6",
    "FEATURE_RECIPE_6c3341a29c915ac7d4c0ab2922b9cea2d64ec6ae012b1fec62de547d0cc83af5"
  ];
  function render() {
    // The fixed examples remain illustrative when inspected in offline tools.
    example.textContent = JSON.stringify({
      request_id: "<new canonical UUID>",
      feature: {id: features.includes(feature.value) ? feature.value : features[0], version: "1.0.0"},
      target_family: "price_return",
      scope: {id: ["EURUSD", "GBPUSD", "USDJPY"].includes(scope.value) ? scope.value : "EURUSD", version: "1.0.0"},
      expected_direction: "DISCOVERY_SIGN_V1"
    }, null, 2);
  }
  for (const field of [feature, scope, target]) field.addEventListener("change", render);
  render();
})();
