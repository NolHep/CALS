(function () {
  "use strict";

  var form = document.getElementById("search-form");
  var locationInput = document.getElementById("location");
  var keywordsInput = document.getElementById("keywords");
  var daysSelect = document.getElementById("days");
  var strictBox = document.getElementById("strict");
  var appealsBox = document.getElementById("appeals");
  var submitButton = document.getElementById("submit");
  var topicsBox = document.getElementById("topics");
  var statusBox = document.getElementById("status");
  var summaryBox = document.getElementById("summary");
  var resultsBox = document.getElementById("results");

  var topicLabels = {};
  var selectedTopics = [];

  function setStatus(message, kind) {
    if (!message) {
      statusBox.hidden = true;
      statusBox.textContent = "";
      return;
    }
    statusBox.hidden = false;
    statusBox.className = "status" + (kind ? " " + kind : "");
    statusBox.textContent = message;
  }

  function loadTopics() {
    fetch("/api/topics")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        data.topics.forEach(function (topic) {
          topicLabels[topic.key] = topic.label;
          var chip = document.createElement("button");
          chip.type = "button";
          chip.className = "chip";
          chip.textContent = topic.label;
          chip.setAttribute("aria-pressed", "false");
          chip.addEventListener("click", function () {
            var index = selectedTopics.indexOf(topic.key);
            if (index === -1) {
              selectedTopics.push(topic.key);
              chip.setAttribute("aria-pressed", "true");
            } else {
              selectedTopics.splice(index, 1);
              chip.setAttribute("aria-pressed", "false");
            }
          });
          topicsBox.appendChild(chip);
        });
      })
      .catch(function () {
        topicsBox.textContent = "Topic filters unavailable.";
      });
  }

  function formatDate(value) {
    if (!value) return "date unknown";
    var parts = String(value).slice(0, 10).split("-");
    if (parts.length !== 3) return value;
    var date = new Date(Date.UTC(+parts[0], +parts[1] - 1, +parts[2]));
    if (isNaN(date.getTime())) return value;
    return date.toLocaleDateString(undefined, {
      year: "numeric", month: "short", day: "numeric", timeZone: "UTC"
    });
  }

  function confidenceBadge(confidence) {
    var badge = document.createElement("span");
    if (confidence >= 0.75) {
      badge.className = "badge strong";
      badge.textContent = "Strong match";
    } else if (confidence >= 0.5) {
      badge.className = "badge";
      badge.textContent = "Likely";
    } else {
      badge.className = "badge weak";
      badge.textContent = "Possible";
    }
    badge.title = "Confidence this docket is a class action: " + confidence;
    return badge;
  }

  function addMeta(parent, text) {
    if (!text) return;
    var span = document.createElement("span");
    span.textContent = text;
    parent.appendChild(span);
  }

  function renderCase(item) {
    var card = document.createElement("article");
    card.className = "case";

    var heading = document.createElement("h3");
    if (item.url) {
      var link = document.createElement("a");
      link.href = item.url;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = item.case_name;
      heading.appendChild(link);
    } else {
      heading.textContent = item.case_name;
    }
    card.appendChild(heading);

    var meta = document.createElement("div");
    meta.className = "meta";
    addMeta(meta, item.court);
    addMeta(meta, "Filed " + formatDate(item.date_filed));
    addMeta(meta, item.docket_number);
    addMeta(meta, item.nature_of_suit);
    meta.appendChild(confidenceBadge(item.confidence));
    card.appendChild(meta);

    if (item.latest_filing) {
      var filing = document.createElement("div");
      filing.className = "meta";
      addMeta(filing, "Latest document: " + item.latest_filing);
      card.appendChild(filing);
    }

    if (item.snippet) {
      var snippet = document.createElement("p");
      snippet.className = "snippet";
      snippet.textContent = item.snippet;
      card.appendChild(snippet);
    }

    if (item.topics && item.topics.length) {
      var tags = document.createElement("div");
      tags.className = "topic-tags";
      item.topics.forEach(function (key) {
        var tag = document.createElement("span");
        tag.className = "topic-tag";
        tag.textContent = topicLabels[key] || key;
        tags.appendChild(tag);
      });
      card.appendChild(tags);
    }

    if (item.confidence_reasons && item.confidence_reasons.length) {
      var why = document.createElement("p");
      why.className = "why";
      why.textContent = "Why: " + item.confidence_reasons.join("; ");
      card.appendChild(why);
    }

    return card;
  }

  function render(data) {
    resultsBox.textContent = "";

    if (!data.cases.length) {
      var empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent =
        "No class actions matched in " + data.query.state_name +
        " for that period. Try a longer window or fewer filters.";
      resultsBox.appendChild(empty);
      summaryBox.hidden = true;
      return;
    }

    summaryBox.hidden = false;
    var courts = data.query.courts.length;
    summaryBox.textContent =
      "Showing " + data.cases.length + " case" +
      (data.cases.length === 1 ? "" : "s") + " from " + courts +
      " federal court" + (courts === 1 ? "" : "s") + " serving " +
      data.query.state_name + ", filed since " + data.query.filed_after +
      (data.cached ? " (cached)" : "") + ".";

    data.cases.forEach(function (item) {
      resultsBox.appendChild(renderCase(item));
    });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var location = locationInput.value.trim();
    if (!location) return;

    submitButton.disabled = true;
    setStatus("Searching federal dockets…", "info");
    resultsBox.textContent = "";
    summaryBox.hidden = true;

    var params = new URLSearchParams({
      location: location,
      keywords: keywordsInput.value.trim(),
      days: daysSelect.value,
      min_confidence: strictBox.checked ? "0.6" : "0.35",
      include_appeals: appealsBox.checked ? "true" : "false",
      topics: selectedTopics.join(",")
    });

    fetch("/api/search?" + params.toString())
      .then(function (response) {
        return response.json().then(function (body) {
          if (!response.ok) {
            throw new Error(body.detail || "Search failed.");
          }
          return body;
        });
      })
      .then(function (data) {
        setStatus(data.notes && data.notes.length ? data.notes.join(" ") : "");
        render(data);
      })
      .catch(function (error) {
        setStatus(error.message || "Something went wrong.");
      })
      .finally(function () {
        submitButton.disabled = false;
      });
  });

  loadTopics();
})();
