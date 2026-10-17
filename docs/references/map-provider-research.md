# Map provider decision — checked 2026-10-17

**Primary sources:**
- Mapbox mobile pricing (25k free monthly active users; first paid tier $4/1k): https://www.mapbox.com/pricing
- Mapbox Standard style + 3D: https://docs.mapbox.com/map-styles/guides/standard-styles/
- React Native bridge is community-maintained: https://docs.mapbox.com/help/glossary/maps-sdk-for-react-native/
- Expo setup requires a custom development build, not Expo Go: https://github.com/rnmapbox/maps/blob/main/plugin/install.md
- MapLibre React Native Expo also needs a custom build: https://maplibre.org/maplibre-react-native/docs/setup/expo/
- MapTiler free/flex pricing, sessions vs tile requests: https://www.maptiler.com/cloud/pricing/ ; https://docs.maptiler.com/guides/account/sessions-vs-requests/
- Mapbox Directions walking parameters: https://docs.mapbox.com/api/navigation/directions/
- Google Solar permitted use: https://cloud.google.com/maps-platform/terms/maps-service-terms
- Google Solar display: https://developers.google.com/maps/documentation/solar/policies

**Decision:** Mapbox Maps SDK through RN bridge, own routing. Do not purchase Navigation SDK just for route drawing. Scope and monitor token usage. Confirm actual license and SDK version compatibility during G0 spike.

**Alternative:** MapLibre React Native + separately licensed map styles/tiles (including MapTiler) if Mapbox cost/vendor terms become problematic. MapTiler is principally useful here as a hosted tile/style provider, not a drop-in RN navigation engine. Leaflet is web-oriented and not appropriate for a native 3D navigation target.

**Pricing caveat:** mobile MAU != web map loads; Search, Directions, Navigation, weather, builds/hosting can bill separately. All current pricing needs to be rechecked before a production launch.
