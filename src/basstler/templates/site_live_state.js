var siteMinimumRecheckMilliseconds = 60000;

function siteLiveStateOf(pullRequest) {
  var labels = (pullRequest["{{ vocabulary.pull_request_field.LABELS.key }}"] || []).map(function (label) {
    return typeof label === "string" ? label : label.name;
  });
  if (pullRequest["{{ vocabulary.pull_request_field.MERGED_AT.key }}"] || labels.indexOf("{{ vocabulary.github_label.MERGED }}") !== -1) {
    return "{{ vocabulary.live_state.MERGED.value }}";
  }
  if (pullRequest["{{ vocabulary.pull_request_field.STATE.key }}"] !== "{{ vocabulary.pull_request_state.OPEN.value }}") {
    return "{{ vocabulary.live_state.CLOSED_UNMERGED.value }}";
  }
  return pullRequest["{{ vocabulary.pull_request_field.DRAFT.key }}"]
    ? "{{ vocabulary.live_state.OPEN_DRAFT.value }}"
    : "{{ vocabulary.live_state.OPEN_READY.value }}";
}

function siteRecheckWhenShown(recheck) {
  var lastRecheck = Date.now();
  recheck();
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible"
      && Date.now() - lastRecheck > siteMinimumRecheckMilliseconds) {
      lastRecheck = Date.now();
      recheck();
    }
  });
}
