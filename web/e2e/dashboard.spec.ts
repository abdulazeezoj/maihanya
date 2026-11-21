import { expect, type Page, test } from "@playwright/test";

const API_ORIGIN = "http://127.0.0.1:9999";

const SCENARIOS = [
  {
    id: "sapon-peak",
    name: "Sapon Under-bridge: Peak Hour",
    status: "idle",
    seed: 1001,
  },
  {
    id: "sapon-offpeak",
    name: "Sapon Under-bridge: Off-Peak",
    status: "idle",
    seed: 1002,
  },
];

const DECISIONS = [
  {
    tick: 2,
    timestamp: "2026-03-03T07:30:02Z",
    recommendation: { recommendedPhase: "NORTH_GREEN", confidence: 0.91 },
    appliedPhase: "NORTH_GREEN",
    reasonCode: "model_accepted",
    reasonDetail: null,
  },
  {
    tick: 1,
    timestamp: "2026-03-03T07:30:01Z",
    recommendation: null,
    appliedPhase: "EAST_GREEN",
    reasonCode: "emergency_preempt",
    reasonDetail: "Emergency vehicle detected on east approach",
  },
];

const EVALUATION = [
  {
    controller: "intelligent",
    scenarioId: "sapon-peak",
    avgWaitingTimeSec: 20.5,
    avgQueueLength: 3.1,
    throughputVehPerHour: 900,
    priorityResponseTimeSec: 12.4,
  },
  {
    controller: "fixed-time",
    scenarioId: "sapon-peak",
    avgWaitingTimeSec: 35.2,
    avgQueueLength: 6.4,
    throughputVehPerHour: 780,
    priorityResponseTimeSec: 40.1,
  },
];

const NETWORK_GEOMETRY = {
  bounds: { minX: 0, minY: 0, maxX: 300, maxY: 300 },
  lanes: [
    {
      id: "north_in_0",
      edgeId: "north_in",
      direction: "north",
      kind: "in",
      shape: [
        [148.4, 300],
        [148.4, 157.2],
      ],
    },
    {
      id: "south_in_0",
      edgeId: "south_in",
      direction: "south",
      kind: "in",
      shape: [
        [151.6, 0],
        [151.6, 142.8],
      ],
    },
    {
      id: "east_in_0",
      edgeId: "east_in",
      direction: "east",
      kind: "in",
      shape: [
        [300, 151.6],
        [157.2, 151.6],
      ],
    },
    {
      id: "west_in_0",
      edgeId: "west_in",
      direction: "west",
      kind: "in",
      shape: [
        [0, 148.4],
        [142.8, 148.4],
      ],
    },
  ],
};

async function mockApi(page: Page) {
  await page.route(`${API_ORIGIN}/api/scenarios/*/network`, (route) =>
    route.fulfill({ json: NETWORK_GEOMETRY }),
  );
  await page.route(`${API_ORIGIN}/api/scenarios`, (route) =>
    route.fulfill({ json: SCENARIOS }),
  );
  await page.route(`${API_ORIGIN}/api/controls/*/run`, (route) =>
    route.fulfill({ json: { ...SCENARIOS[0], status: "running" } }),
  );
  await page.route(`${API_ORIGIN}/api/snapshots/*/decisions*`, (route) =>
    route.fulfill({ json: DECISIONS }),
  );
  await page.route(`${API_ORIGIN}/api/snapshots/*/evaluation`, (route) =>
    route.fulfill({ json: EVALUATION }),
  );
}

test.beforeEach(async ({ page, context }) => {
  await context.addInitScript(() => window.localStorage.clear());
  await mockApi(page);
});

test("live state page lists scenarios from the API and can run one", async ({
  page,
}) => {
  await page.goto("/");

  const picker = page.getByRole("combobox", { name: /select scenario/i });
  await picker.click();
  await expect(
    page.getByRole("option", { name: /Sapon Under-bridge: Peak Hour/i }),
  ).toBeVisible();
  await expect(
    page.getByRole("option", { name: /Sapon Under-bridge: Off-Peak/i }),
  ).toBeVisible();

  await page
    .getByRole("option", { name: /Sapon Under-bridge: Peak Hour/i })
    .click();
  const [request] = await Promise.all([
    page.waitForRequest(`${API_ORIGIN}/api/controls/sapon-peak/run`),
    page.getByRole("button", { name: "Run" }).click(),
  ]);
  expect(request.method()).toBe("POST");
});

test("live junction view renders a Pixi canvas once a scenario's geometry loads", async ({
  page,
}) => {
  await page.goto("/");

  await page.getByRole("combobox", { name: /select scenario/i }).click();
  await page
    .getByRole("option", { name: /Sapon Under-bridge: Peak Hour/i })
    .click();
  const junction = page.getByRole("img", { name: /live junction simulation/i });
  await expect(junction).toBeVisible();
  await expect(junction.locator("canvas")).toBeVisible();
});

test("direction guide stays fixed while the map zooms and pans", async ({
  page,
}) => {
  await page.route("**/api/scenarios/*/network", (route) =>
    route.fulfill({ json: NETWORK_GEOMETRY }),
  );
  await page.route("**/api/scenarios", (route) =>
    route.fulfill({ json: SCENARIOS }),
  );
  await page.goto("/");
  await page.getByRole("combobox", { name: /select scenario/i }).click();
  await page
    .getByRole("option", { name: /Sapon Under-bridge: Peak Hour/i })
    .click();
  const guide = page.getByTestId("junction-directions");
  const canvas = page
    .getByRole("img", { name: /live junction simulation/i })
    .locator("canvas");
  await expect(guide).toHaveText(/N ↑.*E →.*S ↓.*W ←/);
  const relativePosition = () =>
    guide.evaluate((element) => {
      const guideBox = element.getBoundingClientRect();
      const hostBox = element.closest('[role="img"]')?.getBoundingClientRect();
      if (!hostBox) throw new Error("Missing junction host");
      return { x: guideBox.x - hostBox.x, y: guideBox.y - hostBox.y };
    });
  const before = await relativePosition();
  await page.locator('button[aria-label="Zoom out"]').click();
  const box = await canvas.boundingBox();
  if (!box) throw new Error("Missing canvas");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(
    box.x + box.width / 2 + 35,
    box.y + box.height / 2 + 20,
  );
  await page.mouse.up();
  const after = await relativePosition();
  expect(after.x).toBeCloseTo(before.x, 1);
  expect(after.y).toBeCloseTo(before.y, 1);
  await page.setViewportSize({ width: 390, height: 844 });
  const guideBox = await guide.boundingBox();
  const controlBox = await page
    .locator('button[aria-label="Zoom out"]')
    .boundingBox();
  if (!guideBox || !controlBox)
    throw new Error("Missing guide or zoom control");
  expect(guideBox.y + guideBox.height).toBeLessThanOrEqual(controlBox.y);
});

test("road arms remain paved where they meet the junction at multiple zoom levels", async ({
  page,
}) => {
  await page.route("**/api/scenarios/*/network", (route) =>
    route.fulfill({ json: NETWORK_GEOMETRY }),
  );
  await page.route("**/api/scenarios", (route) =>
    route.fulfill({ json: SCENARIOS }),
  );
  await page.goto("/");
  await page.getByRole("combobox", { name: /select scenario/i }).click();
  await page
    .getByRole("option", { name: /Sapon Under-bridge: Peak Hour/i })
    .click();
  const canvas = page
    .getByRole("img", { name: /live junction simulation/i })
    .locator("canvas");
  await expect(canvas).toBeVisible();
  for (const zoom of [5, 5 / 1.5]) {
    if (zoom < 5) await page.locator('button[aria-label="Zoom out"]').click();
    await expect
      .poll(
        async () => {
          const png = await canvas.screenshot();
          return page.evaluate(
            async ({ data, zoomLevel }) => {
              const image = new Image();
              image.src = `data:image/png;base64,${data}`;
              await image.decode();
              const probe = document.createElement("canvas");
              probe.width = image.width;
              probe.height = image.height;
              const ctx = probe.getContext("2d");
              if (!ctx) throw new Error("Canvas 2D unavailable");
              ctx.drawImage(image, 0, 0);
              const scale =
                (Math.min(image.width, image.height) / 300) * 0.9 * zoomLevel;
              const cx = image.width / 2;
              const cy = image.height / 2;
              const paved = [
                [1.6, -5],
                [1.6, 5],
                [-5, 1.6],
                [5, 1.6],
                [-3.6, -3.6],
                [-3.6, 3.6],
                [3.6, -3.6],
                [3.6, 3.6],
              ].every(([x, y]) => {
                const [r, g, b] = ctx.getImageData(
                  Math.round(cx + x * scale),
                  Math.round(cy + y * scale),
                  1,
                  1,
                ).data;
                return r < 70 && g < 70 && b < 70;
              });
              const outside = [
                [-6.5, -6.5],
                [-6.5, 6.5],
                [6.5, -6.5],
                [6.5, 6.5],
              ].every(([x, y]) => {
                const [r, g, b] = ctx.getImageData(
                  Math.round(cx + x * scale),
                  Math.round(cy + y * scale),
                  1,
                  1,
                ).data;
                return g > r && g > b && g > 70;
              });
              return paved && outside;
            },
            { data: png.toString("base64"), zoomLevel: zoom },
          );
        },
        { timeout: 15_000 },
      )
      .toBe(true);
  }
});

test("decision log page renders decisions with a dash for bypassed recommendations", async ({
  page,
}) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("mahanya:selectedScenarioId", "sapon-peak");
  });
  await page.goto("/decisions");

  const table = page.getByRole("table");
  await expect(table.getByText("model_accepted")).toBeVisible();
  await expect(table.getByText("emergency_preempt")).toBeVisible();
  await expect(table.getByText("-")).toBeVisible();
});

test("evaluation page runs a comparison and shows both controllers", async ({
  page,
}) => {
  await page.addInitScript(() => {
    window.localStorage.setItem("mahanya:selectedScenarioId", "sapon-peak");
  });
  await page.goto("/evaluation");

  await page.getByRole("button", { name: /run evaluation/i }).click();

  await expect(page.getByText("20.5 s")).toBeVisible();
  await expect(page.getByText(/Fixed-time baseline: 35.2 s/)).toBeVisible();
});

test("live state page shows the scenario picker and an empty state when none is chosen", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("combobox", { name: /select scenario/i }),
  ).toBeVisible();
  await expect(
    page.getByText(/no live state yet\. select and run/i),
  ).toBeVisible();
});
