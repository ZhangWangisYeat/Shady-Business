# Shady Business

**The only shady business we want you to know about.**

Shady Business is a mobile navigation app we built for LA Hacks 2026 that helps users find walking routes with more shade. Rather than always recommending the shortest path, it considers temperature, sunlight exposure, and the surrounding environment to find routes that balance walking time with comfort.

The idea is fairly simple: the fastest route isn't necessarily the best one, especially when it's 90°F outside.

We started by focusing on UCLA, where students regularly walk between buildings, dining halls, and dorms across a fairly large and hilly campus. Our goal was to build something that could make these everyday walks a little more comfortable while also being practical enough to eventually expand beyond UCLA.

## What It Does

Shady Business compares three different walking routes:

- **Fastest:** The shortest available walking route, without prioritizing shade.
- **Recommended:** Balances walking time and shade coverage based on the current temperature. On cooler days, it prioritizes efficiency; as temperatures increase, it places more weight on avoiding direct sunlight.
- **Most Shade:** Prioritizes shade coverage while limiting how much extra time the user has to spend walking.

The app uses a native Mapbox interface to display routes, visualize shade coverage, and guide users between locations. It also distinguishes between shaded, sun-exposed, and unknown areas rather than assuming incomplete data is automatically sunny.

Users can select UCLA landmarks, compare their available routes, and use guided navigation or a simulated demo walk to see how the routing works.

## The Problem We Ran Into

One of the biggest challenges wasn't actually calculating the routes themselves. It was getting enough geographic information to calculate how much shade each route would have.

Our original tree and building datasets covered central UCLA fairly well, but had significant gaps around the hill dorms. Some of our test routes had **31–55% unknown coverage**, meaning our routing algorithm couldn't properly compare the alternatives.

Manually mapping and measuring every missing tree or building wasn't particularly realistic, especially within a hackathon. So instead, we built another tool to help solve the problem.

## VisionLab: Our AI Vision Agent

[VisionLab](https://agentverse.ai/) is an AI-powered computer vision agent we developed to turn aerial imagery into structured geographic data.

It retrieves aerial imagery for a specified location and uses trained machine learning models to identify features such as trees, buildings, vegetation, water, and shadows. It then converts those detections into geographic polygons, calculates measurements, and returns the results as structured JSON.

More importantly, **VisionLab compares its detections against existing datasets to identify what's missing.** It can also estimate unrecorded measurements, such as tree and building heights, using models trained on real-world measurements.

Its main capabilities include:

- **Object detection:** Identify and outline trees, buildings, vegetation, water, and other geographic features.
- **Geographic measurements:** Calculate areas, canopy coverage, and individual object boundaries.
- **Dataset comparison:** Identify missing objects and incomplete geographic coverage.
- **Predictive modeling:** Estimate tree and building heights from measured training data.
- **Custom training:** Learn new object categories from labeled GeoJSON examples.
- **Automated analysis:** Handle imagery retrieval, detection, comparison, and prediction through a single agent workflow.

VisionLab uses USDA NAIP aerial imagery, including near-infrared data, alongside gradient-boosted classifiers and spectral models. Its height prediction models achieved mean errors of **4.6 m for trees** and **6.5 m for buildings** on held-out test data.

The agent is registered on **Agentverse**, built with `uAgents`, and uses the **Agent Chat Protocol (ACP)**.

**Agent address:**
`agent1qf0kxk6uevd2hq98lsxtdzn6wgv7dphk6p6jn22kmp5e3jh9u7yc78k2j9e`

Although we initially developed VisionLab for Shady Business, we designed it as a more general-purpose agent. The same system could be used for property analysis, solar planning, urban mapping, environmental monitoring, or other applications that depend on geographic data.

## Results

We used VisionLab to analyze the areas around UCLA where our original geographic datasets were incomplete.

In under a minute, it processed **16 aerial imagery tiles**, identifying:

- **896 additional trees** with estimated heights and crown boundaries.
- **137 additional buildings** with footprints and estimated heights.

We then reran the same walking routes under identical conditions to see how the additional data affected our routing algorithm.

| Walking Route (1 PM, 90°F) | Unknown Coverage Before → After | Route Options | Shadiest Route |
|---|---|---|---|
| Olympic Hall → Royce Hall | 45% → **0%** | 1 → **3** | 68% shade |
| Bruin Plate → Royce Hall | 31% → **0%** | 1 → **3** | 70% shade |
| Hedrick Hall → Powell Library | 55% → **0%** | 1 → **3** | 68% shade |

The biggest improvement wasn't necessarily changing the routing algorithm, but giving it enough information to make meaningful comparisons in the first place.

These results come from our modeled route tests, rather than field measurements. Predicted tree and building heights are kept separate from observed measurements, and existing measured data takes priority.

## Tech Stack

| Component | Technology |
|---|---|
| **Mobile frontend** | React Native, Expo, TypeScript |
| **Maps and navigation** | Mapbox Maps SDK |
| **Backend** | Python, FastAPI |
| **Routing** | OpenStreetMap, OSMnx, NetworkX |
| **Shade modeling** | Sun position, building geometry, tree canopy, and temperature-aware routing |
| **Computer vision** | VisionLab, gradient-boosted classifiers, spectral analysis |
| **Geographic data** | USDA NAIP, UCLA ArborPro, OpenStreetMap |
| **AI agent infrastructure** | uAgents, Agentverse, ACP |
| **Mobile builds** | Expo Application Services (EAS) |

### How Routing Works

Our backend uses real pedestrian paths retrieved from OpenStreetMap to generate candidate walking routes around UCLA.

For each route, the system evaluates walking time and available shade information. Tree and building geometries are used alongside sun position to model shadows, while the temperature influences how much additional walking time is reasonable to avoid direct sunlight.

The Most Shade option applies a detour limit so users aren't asked to take unnecessarily long routes just to spend a little more time in the shade.

These are modeled estimates, not real-time measurements of sunlight on the ground. Route generation currently uses candidate-path search rather than a guaranteed globally optimal shade solution.

## Getting Started

The project is structured around a React Native mobile frontend and a FastAPI backend.

### 1. Backend

From the repository root:

```bash
cd backend
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

python -m pip install -e ".[dev,ingest]"
python -m pytest -q
```

Download the UCLA walking network and start the backend:

```bash
cd ..
python scripts/fetch_ucla_graph.py --confirm-network

cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The API can be accessed at `http://localhost:8000/docs`.

### 2. Mobile

Requires Node.js 22+ and a native development build because Mapbox's native SDK is not supported in Expo Go.

```bash
cd mobile
npm install
npx expo install --fix
```

Copy `.env.example` to `.env` and configure your public Mapbox access token and backend API URL.

To run the development client:

```bash
npx expo start --dev-client
```

For local development, your phone must be able to reach the backend through your computer's LAN IP.

### 3. EAS Builds

We've incorporated Expo Application Services (EAS) into our mobile build workflow so we can create standalone builds without relying on local Android Studio or Xcode installations.

To configure EAS and create an Android preview build:

```bash
npm install -g eas-cli
eas login
eas build:configure
eas build --platform android --profile preview
```

The `preview` profile should use internal distribution and produce an installable Android APK. Once built, the APK can be installed directly on an Android device without Expo Go or a continuously connected development computer.

For standalone testing, the app must use a publicly reachable backend rather than `localhost` or a local network address. Native Mapbox build credentials must also be configured securely through EAS and should never be committed to the repository.

See the [Expo EAS documentation](https://docs.expo.dev/build/setup/) for additional configuration details.

## Future Plans

Shady Business is currently a hackathon prototype, but we'd like to continue developing it into a publicly available mobile app for **both iPhone and Android**.

Some of our next priorities include:

- **Expanding beyond UCLA:** Supporting other university campuses and eventually more general walking navigation.
- **Improving shade accuracy:** Incorporating additional geographic measurements, more detailed 3D building data, and better tree canopy models.
- **Live conditions:** Using updated weather and sun-position data to adjust route recommendations throughout the day.
- **Improving navigation:** Refining GPS guidance, route recalculation, and the overall mobile experience.
- **Public mobile release:** Completing device testing, deploying the backend, and preparing builds for distribution through the Apple App Store and Google Play.

We're using EAS to make testing and distribution easier as we work toward that goal. Public store releases will follow once the routing, backend reliability, and on-device performance have been sufficiently tested.

## Project Structure

```text
mobile/                 # React Native / Expo frontend
backend/                # FastAPI, routing, shade calculations
backend/tests/          # Backend tests
scripts/                # Data retrieval and preprocessing
docs/                   # Architecture, data sources, API contracts
AGENTS.md               # Shared development guidelines
CLAUDE.md               # Claude Code configuration
.github/workflows/      # CI workflows
```

We used both Claude Code and Codex during development, with separate feature branches and shared project instructions to coordinate frontend, backend, and model development.

Additional documentation is available in:

- [Architecture and shade modeling](docs/architecture.md)
- [API contracts](docs/api-contracts.md)
- [UCLA geographic data sources](docs/references/ucla-source-catalog.md)
- [Development progress](docs/progress.md)

## Data and Licensing

- **USDA NAIP:** Public-domain aerial imagery used for VisionLab's detection and analysis.
- **OpenStreetMap:** Walking networks and geographic features, © OpenStreetMap contributors (ODbL).
- **UCLA ArborPro:** Tree inventory used for model training, evaluation, and geographic comparison.
- **Mapbox:** Native mapping SDK, subject to Mapbox's licensing and usage terms.

API credentials, private tokens, downloaded geographic datasets, and sensitive location traces should not be committed to the repository.

---

## Why We Built This

Shady Business started with a fairly straightforward idea: walking around campus in the heat shouldn't mean having to choose between taking the fastest route and staying comfortable.

As we worked on it, we realized that the bigger challenge was making sense of geographic data that was often incomplete or missing entirely. Building VisionLab gave us a way to address that problem without manually collecting every measurement ourselves.

Ultimately, we wanted to build something that could make everyday navigation a little more practical, while also developing tools that could be useful for other projects facing similar problems.
