var planPageLiveStates = {{ vocabulary.live_state_display.state_chips | tojson }};
var planPageDoneStatus = {{ vocabulary.live_state_display.done_status | tojson }};
var planPageChipTones = {{ vocabulary.live_state_display.chip_tones | tojson }};
var planPageRelativeTimeMilliseconds = 30000;

function planPageUnblocksDependents(pullRequest) {
  return pullRequest["{{ vocabulary.pull_request_field.MERGED_AT.key }}"] !== null
    || (pullRequest["{{ vocabulary.pull_request_field.STATE.key }}"] === "{{ vocabulary.pull_request_state.OPEN.value }}"
      && !pullRequest["{{ vocabulary.pull_request_field.DRAFT.key }}"]);
}

function planPageMarkDependencyReady(chip) {
  chip.classList.remove("chip-unmet");
  chip.title = chip.getAttribute("{{ vocabulary.draft_recheck_attribute.READY_TITLE }}");
  var card = chip.closest(".item");
  if (card.querySelector(".chip-unmet")) {
    return;
  }
  var startAction = card.querySelector("[{{ vocabulary.draft_recheck_attribute.START_ACTION }}]");
  if (startAction) {
    startAction.hidden = false;
  }
}

function planPageChangeCount(status, change) {
  var count = document.querySelector("[{{ vocabulary.live_state_attribute.STATUS_COUNT }}=\"" + status + "\"]");
  if (count) {
    count.textContent = String(Number(count.textContent) + change);
  }
}

function planPageMarkItemDone(card) {
  var status = card.getAttribute("{{ vocabulary.live_state_attribute.ITEM_STATUS }}");
  if (status === planPageDoneStatus.status) {
    return;
  }
  Array.prototype.slice.call(card.classList).forEach(function (className) {
    if (className.indexOf("status-") === 0) {
      card.classList.remove(className);
    }
  });
  card.classList.add(planPageDoneStatus.css_class);
  card.setAttribute("{{ vocabulary.live_state_attribute.ITEM_STATUS }}", planPageDoneStatus.status);
  var statusChip = card.querySelector("[{{ vocabulary.live_state_attribute.STATUS_CHIP }}]");
  statusChip.className = "chip " + planPageDoneStatus.tone;
  statusChip.textContent = planPageDoneStatus.label;
  planPageChangeCount(status, -1);
  planPageChangeCount(planPageDoneStatus.status, 1);
}

function planPageShowLiveState(chip, stateName) {
  var shown = planPageLiveStates[stateName];
  planPageChipTones.forEach(function (tone) {
    chip.classList.remove(tone);
  });
  chip.classList.add(shown.tone);
  chip.textContent = chip.textContent.split(" · ")[0] + " · " + shown.label;
  if (stateName === "{{ vocabulary.live_state.MERGED.value }}") {
    planPageMarkItemDone(chip.closest(".item"));
  }
}

function planPageDescribeAge(milliseconds) {
  var minutes = Math.floor(milliseconds / 60000);
  if (minutes < 1) {
    return "just now";
  }
  if (minutes < 60) {
    return minutes + (minutes === 1 ? " minute ago" : " minutes ago");
  }
  var hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return hours + (hours === 1 ? " hour ago" : " hours ago");
  }
  var days = Math.floor(hours / 24);
  return days + (days === 1 ? " day ago" : " days ago");
}

function planPageShowRelativeTimes() {
  document.querySelectorAll("[{{ vocabulary.plan_time_attribute.RELATIVE }}]").forEach(function (time) {
    var moment = new Date(time.getAttribute("datetime"));
    time.title = moment.toLocaleString();
    time.textContent = planPageDescribeAge(Date.now() - moment.getTime());
  });
}

function planPageShowRefresh(refused) {
  var refreshed = document.querySelector("[{{ vocabulary.plan_time_attribute.REFRESHED }}]");
  var source = document.querySelector("[{{ vocabulary.plan_time_attribute.REFRESH_SOURCE }}]");
  if (!refreshed || !source) {
    return;
  }
  if (refused) {
    source.textContent = "{{ vocabulary.refresh_source.REFUSED }}";
    return;
  }
  refreshed.setAttribute("datetime", new Date().toISOString());
  source.textContent = "{{ vocabulary.refresh_source.LIVE }}";
  planPageShowRelativeTimes();
}

function planPageRecheckPullRequests() {
  var chipsByAddress = {};
  function chipsOf(address) {
    return chipsByAddress[address] = chipsByAddress[address] || { dependencies: [], items: [] };
  }
  document.querySelectorAll("[{{ vocabulary.draft_recheck_attribute.PULL_REQUEST }}]").forEach(function (chip) {
    chipsOf(chip.getAttribute("{{ vocabulary.draft_recheck_attribute.PULL_REQUEST }}")).dependencies.push(chip);
  });
  document.querySelectorAll("[{{ vocabulary.live_state_attribute.PULL_REQUEST }}]").forEach(function (chip) {
    chipsOf(chip.getAttribute("{{ vocabulary.live_state_attribute.PULL_REQUEST }}")).items.push(chip);
  });
  var addresses = Object.keys(chipsByAddress);
  var refused = false;
  var rechecks = addresses.map(function (address) {
    var chips = chipsByAddress[address];
    return fetch(address)
      .then(function (response) {
        // GitHub answers a private repository's pull request with 404 without a token,
        // so no refusal changes what the build showed.
        if (!response.ok) {
          refused = true;
          return null;
        }
        return response.json();
      })
      .then(function (pullRequest) {
        if (!pullRequest) {
          return;
        }
        if (planPageUnblocksDependents(pullRequest)) {
          chips.dependencies.forEach(planPageMarkDependencyReady);
        }
        var stateName = siteLiveStateOf(pullRequest);
        chips.items.forEach(function (chip) {
          planPageShowLiveState(chip, stateName);
        });
      })
      .catch(function () {
        refused = true;
      });
  });
  Promise.all(rechecks).then(function () {
    if (addresses.length) {
      planPageShowRefresh(refused);
    }
    document.getElementById("plan-page")
      .setAttribute("{{ vocabulary.draft_recheck_attribute.FINISHED }}", "");
  });
}

function planPageStartRechecks() {
  planPageShowRelativeTimes();
  siteRecheckWhenShown(planPageRecheckPullRequests);
  setInterval(planPageShowRelativeTimes, planPageRelativeTimeMilliseconds);
}
