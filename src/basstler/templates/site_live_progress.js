var siteReachedStages = {{ vocabulary.live_state_display.reached_stages | tojson }};

function siteListLiveStates(listingUrl, numbers) {
  var states = {};
  var oldest = Math.min.apply(null, numbers);
  function readPage(page) {
    return fetch(listingUrl + "&{{ vocabulary.page_parameter.PAGE }}=" + page)
      .then(function (response) {
        // GitHub answers a private repository's listing with 404 without a token, so
        // a refusal keeps what the build counted.
        return response.ok ? response.json() : [];
      })
      .then(function (pullRequests) {
        pullRequests.forEach(function (pullRequest) {
          states[pullRequest["{{ vocabulary.pull_request_field.NUMBER.key }}"]] = siteLiveStateOf(pullRequest);
        });
        var unread = numbers.some(function (number) {
          return !(number in states);
        });
        var last = pullRequests[pullRequests.length - 1];
        if (unread && pullRequests.length === {{ vocabulary.pull_requests_per_page }}
          && last["{{ vocabulary.pull_request_field.NUMBER.key }}"] > oldest) {
          return readPage(page + 1);
        }
      });
  }
  return readPage(1)
    .catch(function () {})
    .then(function () {
      return states;
    });
}

function sitePercentage(count, total) {
  return total ? count / total * 100 : 0;
}

// Rounds half to even, as the build's whole percentages do.
function siteWholePercentage(percentage) {
  var rounded = Math.round(percentage);
  return rounded - percentage === 0.5 && rounded % 2 !== 0 ? rounded - 1 : rounded;
}

function siteFillLabel(element, placeholder, value) {
  return element.getAttribute("{{ vocabulary.progress_card_attribute.LABEL_FORMAT }}").replace(placeholder, String(value));
}

function siteShowProgress(card, items, statesByListing) {
  var counts = {};
  {{ vocabulary.progress_stage | map(attribute="value") | list | tojson }}.forEach(function (stage) {
    counts[stage] = 0;
  });
  items.forEach(function (item) {
    var listed = item.listing_url ? statesByListing[item.listing_url][item.number] : undefined;
    siteReachedStages[item.status][listed || item.live_state].forEach(function (stage) {
      counts[stage] += 1;
    });
  });
  var progress = card.querySelector("[{{ vocabulary.progress_card_attribute.PROGRESS }}]");
  progress.textContent = siteFillLabel(progress, "{{ vocabulary.label_placeholder.DONE }}", counts["{{ vocabulary.progress_stage.DONE }}"]);
  card.querySelectorAll("[{{ vocabulary.progress_card_attribute.STAGE_LABEL }}]").forEach(function (label) {
    var stage = label.getAttribute("{{ vocabulary.progress_card_attribute.STAGE_LABEL }}");
    label.textContent = siteFillLabel(label, "{{ vocabulary.label_placeholder.PERCENTAGE }}",
      siteWholePercentage(sitePercentage(counts[stage], items.length)));
  });
  card.querySelectorAll("[{{ vocabulary.progress_card_attribute.STAGE_BAR }}]").forEach(function (bar) {
    var percentage = sitePercentage(counts[bar.getAttribute("{{ vocabulary.progress_card_attribute.STAGE_BAR }}")], items.length);
    bar.style.width = percentage.toFixed(1) + "%";
    bar.title = siteFillLabel(bar, "{{ vocabulary.label_placeholder.PERCENTAGE }}", siteWholePercentage(percentage));
  });
  if (card.classList.contains("{{ vocabulary.progress_card.card_css_class }}")) {
    card.classList.toggle("{{ vocabulary.progress_card.complete_css_class }}",
      items.length > 0 && counts["{{ vocabulary.progress_stage.DONE }}"] === items.length);
  }
}

function siteRecountProgress() {
  var cards = Array.prototype.map.call(
    document.querySelectorAll("[{{ vocabulary.progress_card_attribute.COUNTED_ITEMS }}]"),
    function (card) {
      return { element: card, items: JSON.parse(card.getAttribute("{{ vocabulary.progress_card_attribute.COUNTED_ITEMS }}")) };
    });
  var numbersByListing = {};
  cards.forEach(function (card) {
    card.items.forEach(function (item) {
      if (item.listing_url) {
        (numbersByListing[item.listing_url] = numbersByListing[item.listing_url] || []).push(item.number);
      }
    });
  });
  var statesByListing = {};
  var listings = Object.keys(numbersByListing).map(function (listingUrl) {
    return siteListLiveStates(listingUrl, numbersByListing[listingUrl]).then(function (states) {
      statesByListing[listingUrl] = states;
    });
  });
  Promise.all(listings).then(function () {
    cards.forEach(function (card) {
      siteShowProgress(card.element, card.items, statesByListing);
    });
    document.getElementById("site-page")
      .setAttribute("{{ vocabulary.progress_card_attribute.FINISHED }}", "");
  });
}
