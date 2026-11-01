function planSiteUnblocksDependents(pullRequest) {
  return pullRequest["{{ pull_request_field.MERGED_AT.key }}"] !== null
    || (pullRequest["{{ pull_request_field.STATE.key }}"] === "{{ pull_request_state.OPEN.value }}"
      && !pullRequest["{{ pull_request_field.DRAFT.key }}"]);
}

function planSiteMarkDependencyReady(chip) {
  chip.classList.remove("chip-unmet");
  chip.title = chip.getAttribute("{{ draft_recheck_attribute.READY_TITLE }}");
  var card = chip.closest(".item");
  if (card.querySelector(".chip-unmet")) {
    return;
  }
  var startAction = card.querySelector("[{{ draft_recheck_attribute.START_ACTION }}]");
  if (startAction) {
    startAction.hidden = false;
  }
}

function planSiteRecheckDraftDependencies() {
  var chipsByAddress = {};
  document.querySelectorAll("[{{ draft_recheck_attribute.PULL_REQUEST }}]").forEach(function (chip) {
    var address = chip.getAttribute("{{ draft_recheck_attribute.PULL_REQUEST }}");
    (chipsByAddress[address] = chipsByAddress[address] || []).push(chip);
  });
  var rechecks = Object.keys(chipsByAddress).map(function (address) {
    return fetch(address)
      .then(function (response) {
        return response.ok ? response.json() : null;
      })
      .then(function (pullRequest) {
        if (pullRequest && planSiteUnblocksDependents(pullRequest)) {
          chipsByAddress[address].forEach(planSiteMarkDependencyReady);
        }
      });
  });
  Promise.all(rechecks).then(function () {
    document.getElementById("plan-dashboard-page")
      .setAttribute("{{ draft_recheck_attribute.FINISHED }}", "");
  });
}
