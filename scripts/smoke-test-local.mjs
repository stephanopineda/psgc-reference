const baseUrl = (
  process.env.PSGC_API_URL ?? "http://127.0.0.1:8787"
).replace(/\/$/, "");

let passed = 0;

async function check(name, path, verify) {
  const response = await fetch(`${baseUrl}${path}`);
  let body;

  try {
    body = await response.json();
  } catch {
    throw new Error(`${name}: response was not valid JSON`);
  }

  if (!response.ok) {
    throw new Error(
      `${name}: HTTP ${response.status}: ${JSON.stringify(body)}`,
    );
  }

  await verify(body, response);
  passed += 1;
  console.log(`PASS ${name}`);
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

await check("database health", "/healthz", (body) => {
  assert(body.data?.status === "ok", "API health is not ok");
  assert(body.data?.database === "ok", "Database health is not ok");
});

await check("release list", "/v1/releases", (body) => {
  assert(body.data?.length === 4, "Expected four releases");
  assert(body.meta?.count === 4, "Incorrect release count");
  assert(
    body.data[0]?.release_id === "2026-Q3",
    "Unexpected newest release",
  );
});

await check("release detail", "/v1/releases/2026-Q3", (body) => {
  assert(body.data?.record_count === 43768, "Incorrect record count");
  const findings = body.data?.validation_findings ?? [];
  const warning = findings.find((item) => item.severity === "WARNING");
  const review = findings.find((item) => item.severity === "REVIEW");

  assert(warning?.count === 84, "Expected 84 warnings");
  assert(review?.count === 1, "Expected one review finding");
});

const unpublishedHierarchy = await fetch(
  `${baseUrl}/v1/releases/2026-Q3/locations`,
);
const unpublishedBody = await unpublishedHierarchy.json();

assert(
  unpublishedHierarchy.status === 409,
  "Expected HTTP 409 for an unpublished hierarchy",
);
assert(
  unpublishedBody.error?.code === "HIERARCHY_NOT_PUBLISHED",
  "Unexpected unpublished-hierarchy error code",
);
passed += 1;
console.log("PASS unpublished hierarchy protection");

await check(
  "geographic levels",
  "/v1/geographic-levels?release_id=2026-Q3",
  (body) => {
    assert(body.data?.length === 6, "Expected six classified levels");
    assert(
      body.meta?.unclassified_record_count === 2,
      "Expected two unclassified records",
    );
  },
);

await check(
  "record search and pagination",
  "/v1/records?release_id=2026-Q3&q=Isabela&page=1&page_size=5",
  (body) => {
    assert(body.data?.length === 5, "Expected five records on page one");
    assert(body.meta?.total === 7, "Expected seven matching records");
    assert(body.meta?.total_pages === 2, "Expected two pages");
  },
);

await check(
  "record provenance",
  "/v1/records/0990100000?release_id=2026-Q3",
  (body) => {
    assert(
      body.data?.source_values?.population === "#N/A",
      "Raw source population value was not preserved",
    );

    const event = body.data?.normalization_events?.population;
    assert(
      event?.action === "KNOWN_SOURCE_ERROR_AS_MISSING",
      "Expected source-error normalization event",
    );
    assert(event?.status === "REVIEW", "Expected REVIEW status");
    assert(event?.normalized_value === null, "Expected null normalized value");
  },
);

const missingRelease = await fetch(`${baseUrl}/v1/records`);
const missingBody = await missingRelease.json();

assert(missingRelease.status === 400, "Expected HTTP 400 without release_id");
assert(
  missingBody.error?.code === "RELEASE_REQUIRED",
  "Unexpected missing-release error code",
);
passed += 1;
console.log("PASS explicit release requirement");

console.log(`\n${passed} integration checks passed.`);
