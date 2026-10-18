const { withAndroidManifest } = require('expo/config-plugins');

// the test apk talks to the backend on a laptop over plain http (a local ip has
// no https), and release builds of android refuse http unless you allow it. this
// only switches on when the api url is http, so an https backend later gets the
// safer default back.
const allowHttp = config => withAndroidManifest(config, mod => {
  mod.modResults.manifest.application[0].$['android:usesCleartextTraffic'] = 'true';
  return mod;
});
const usesHttp = (process.env.EXPO_PUBLIC_API_URL ?? '').startsWith('http://');

module.exports = {
  expo: {
    name: 'Shady Business',
    slug: 'shady-business',
    scheme: 'shadybusiness',
    version: '0.1.0',
    orientation: 'portrait',
    userInterfaceStyle: 'light',
    icon: './assets/icon.png',
    android: {
      package: 'com.shadybusiness.app', permissions: ['ACCESS_COARSE_LOCATION', 'ACCESS_FINE_LOCATION'],
      // launchers crop this to a circle or squircle, so the logo sits small in
      // the middle on the logo's own off-white (#FEFEFE) so no square edge shows
      adaptiveIcon: { foregroundImage: './assets/adaptive-icon.png', backgroundColor: '#FEFEFE' },
    },
    ios: { bundleIdentifier: 'com.shadybusiness.app', infoPlist: { NSLocationWhenInUseUsageDescription: 'Show your location to guide your walk.' } },
    plugins: [
      '@rnmapbox/maps',
      'expo-secure-store',
      ['expo-location', { locationWhenInUsePermission: 'Show your location to guide your walk.' }],
      ...(usesHttp ? [allowHttp] : [])
    ],
    extra: { apiBaseUrl: process.env.EXPO_PUBLIC_API_URL }
  }
};
