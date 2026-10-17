module.exports = {
  expo: {
    name: 'Shady Business',
    slug: 'shady-business',
    scheme: 'shadybusiness',
    version: '0.1.0',
    orientation: 'portrait',
    userInterfaceStyle: 'light',
    android: { package: 'com.shadybusiness.app', permissions: ['ACCESS_COARSE_LOCATION', 'ACCESS_FINE_LOCATION'] },
    ios: { bundleIdentifier: 'com.shadybusiness.app', infoPlist: { NSLocationWhenInUseUsageDescription: 'Show your location to guide your walk.' } },
    plugins: [
      '@rnmapbox/maps',
      ['expo-location', { locationWhenInUsePermission: 'Show your location to guide your walk.' }]
    ],
    extra: { apiBaseUrl: process.env.EXPO_PUBLIC_API_URL }
  }
};
