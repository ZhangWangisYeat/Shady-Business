import React, { useMemo } from 'react';
import { StyleSheet, View, Text } from 'react-native';
import Mapbox, { Camera, MapView, ShapeSource, LineLayer, PointAnnotation } from '@rnmapbox/maps';
import type { Coordinate, Route } from '../api/types';

const CENTER: Coordinate = [-118.4452, 34.0689];
const TOKEN=process.env.EXPO_PUBLIC_MAPBOX_TOKEN;
if (TOKEN?.startsWith('pk.')) Mapbox.setAccessToken(TOKEN);

type Props={route: Route | null; position?: Coordinate | null; navigating: boolean};
export function ShadyMap({route,position,navigating}:Props) {
  const geo = useMemo(() => ({
    type: 'FeatureCollection',
    features: (route?.segments ?? []).map((segment,i) => ({
      type: 'Feature', id: i, properties: { shade: segment.shade_state },
      geometry: segment.geometry,
    })),
  }),[route]);
  if (!TOKEN || !TOKEN.startsWith('pk.')) return (
    <View style={styles.missing}><Text style={styles.missingText}>Set EXPO_PUBLIC_MAPBOX_TOKEN to display the real UCLA map.</Text></View>
  );
  return <MapView style={StyleSheet.absoluteFill} styleURL="mapbox://styles/mapbox/standard" compassEnabled>
    <Camera zoomLevel={navigating?17:15} pitch={navigating?50:28} animationDuration={650}
      centerCoordinate={position ?? CENTER}/>
    {route && <ShapeSource id="shady-route" shape={geo as any}>
      <LineLayer id="shady-outline" style={{lineColor:'#ffffff',lineWidth:10,lineOpacity:.9,lineCap:'round',lineJoin:'round'}}/>
      <LineLayer id="shady-color" style={{lineWidth:6,lineOpacity:.98,lineCap:'round',lineJoin:'round',lineColor:
        ['match',['get','shade'],'shade','#27A87A','sun','#F29A38','#78838B'] as any}}/>
    </ShapeSource>}
    {position && <PointAnnotation id="current-position" coordinate={position}>
      <View style={styles.dot}/>
    </PointAnnotation>}
  </MapView>;
}
const styles=StyleSheet.create({
  missing:{...StyleSheet.absoluteFill,justifyContent:'center',alignItems:'center',backgroundColor:'#E6F1EA',padding:30},
  missingText:{textAlign:'center',color:'#234433',fontSize:16},
  dot:{width:18,height:18,borderRadius:9,backgroundColor:'#356FED',borderColor:'#fff',borderWidth:3},
});
