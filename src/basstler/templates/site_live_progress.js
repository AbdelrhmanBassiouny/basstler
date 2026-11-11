{% set item_field = vocabulary.counted_item.field_names %}
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

// Writes a number as the build does: toFixed rounds an exact tie up, Python to even.
function siteFormatHalfToEven(value, decimalPlaces) {
  var rounded = value.toFixed(decimalPlaces);
  var exact = value.toFixed(100);
  var kept = exact.slice(0, exact.indexOf(".") + 1 + decimalPlaces);
  var isTie = /^50*$/.test(exact.slice(kept.length));
  var keptIsEven = Number(kept.charAt(kept.length - 1 - (decimalPlaces ? 0 : 1))) % 2 === 0;
  return isTie && keptIsEven ? kept.replace(/\.$/, "") : rounded;
}

function siteFillFormat(element, formatAttribute, placeholder, value) {
  return element.getAttribute(formatAttribute).replace(placeholder, value);
}

function siteShowProgress(card, items, statesByListing) {
  var counts = {};
  {{ vocabulary.progress_stage | list | tojson }}.forEach(function (stage) {
    counts[stage] = 0;
  });
  items.forEach(function (item) {
    var listingUrl = item["{{ item_field.listing_url }}"];
    var listed = listingUrl ? statesByListing[listingUrl][item["{{ item_field.number }}"]] : undefined;
    siteReachedStages[item["{{ item_field.status }}"]][listed || item["{{ item_field.live_state }}"]].forEach(function (stage) {
      counts[stage] += 1;
    });
  });
  var progress = card.querySelector("[{{ vocabulary.progress_card_attribute.PROGRESS }}]");
  progress.textContent = siteFillFormat(progress, "{{ vocabulary.progress_card_attribute.LABEL_FORMAT }}",
    "{{ vocabulary.label_placeholder.DONE }}", String(counts["{{ vocabulary.progress_stage.DONE }}"]));
  card.querySelectorAll("[{{ vocabulary.progress_card_attribute.STAGE_LABEL }}]").forEach(function (label) {
    var stage = label.getAttribute("{{ vocabulary.progress_card_attribute.STAGE_LABEL }}");
    label.textContent = siteFillFormat(label, "{{ vocabulary.progress_card_attribute.LABEL_FORMAT }}",
      "{{ vocabulary.label_placeholder.PERCENTAGE }}",
      siteFormatHalfToEven(sitePercentage(counts[stage], items.length), {{ vocabulary.stage_share.label_decimal_places }}));
  });
  card.querySelectorAll("[{{ vocabulary.progress_card_attribute.STAGE_BAR }}]").forEach(function (bar) {
    var percentage = sitePercentage(counts[bar.getAttribute("{{ vocabulary.progress_card_attribute.STAGE_BAR }}")], items.length);
    bar.style.width = siteFillFormat(bar, "{{ vocabulary.progress_card_attribute.WIDTH_FORMAT }}",
      "{{ vocabulary.label_placeholder.PERCENTAGE }}",
      siteFormatHalfToEven(percentage, {{ vocabulary.stage_share.width_decimal_places }}));
    bar.title = siteFillFormat(bar, "{{ vocabulary.progress_card_attribute.LABEL_FORMAT }}",
      "{{ vocabulary.label_placeholder.PERCENTAGE }}",
      siteFormatHalfToEven(percentage, {{ vocabulary.stage_share.label_decimal_places }}));
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
      var listingUrl = item["{{ item_field.listing_url }}"];
      if (listingUrl) {
        (numbersByListing[listingUrl] = numbersByListing[listingUrl] || []).push(item["{{ item_field.number }}"]);
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
