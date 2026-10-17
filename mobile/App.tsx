import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, SafeAreaView, StyleSheet, Text, TouchableOpacity, View, ScrollView } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import * as Location from 'expo-location';
import { ShadyMap } from './src/map/ShadyMap';
import { getPlaces, getRoutes } from './src/api/client';
import type { Coordinate, Place, Route, RoutesResponse, ShadeState } from './src/api/types';
import { interpolateRoute, locateOnRoute, statusByTimeFraction } from './src/navigation/progress';

const COLORS={ink:'#203329',green:'#17785D',background:'#FFFFFF'};
const routeName:Record<Route['mode'],string>={fastest:'Fastest',recommended:'Recommended',maximum_shade:'Most shade'};
const statusText:Record<ShadeState,string>={shade:'In shade',sun:'In direct sun',unknown:'Shade unknown'};

type Stage='search'|'compare'|'navigate'|'arrived';
export default function App() {
  const [stage,setStage]=useState<Stage>('search');
  const [places,setPlaces]=useState<Place[]>([]);
  const [origin,setOrigin]=useState('royce-hall');
  const [destination,setDestination]=useState('ackerman-union');
  const [temp,setTemp]=useState(29);
  const [routes,setRoutes]=useState<RoutesResponse|null>(null);
  const [chosen,setChosen]=useState<Route['mode']>('recommended');
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState('');
  const [progress,setProgress]=useState(0);
  const [position,setPosition]=useState<Coordinate|null>(null);
  const [shade,setShade]=useState<ShadeState>('unknown');
  const [demo,setDemo]=useState(false);
  const subscription=useRef<Location.LocationSubscription|null>(null);
  const interval=useRef<ReturnType<typeof setInterval>|null>(null);
  const active=routes?.routes.find(r=>r.mode===chosen) ?? null;
  const stop=()=>{subscription.current?.remove();subscription.current=null; if(interval.current) clearInterval(interval.current);interval.current=null;};
  useEffect(()=>{getPlaces().then(res=>setPlaces(res.places)).catch(e=>setError(e.message));return ()=>stop();},[]);

  const calculate=async()=>{
    if(origin===destination){setError('Choose different start and destination.');return;}
    setLoading(true);setError('');
    try {const response=await getRoutes(origin,destination,temp);setRoutes(response);setChosen('recommended');setStage('compare');}
    catch(e){setError(e instanceof Error?e.message:'Could not calculate route.');}
    finally{setLoading(false);}
  };
  const selected=(mode:Route['mode'])=>{setChosen(mode);setPosition(null);setProgress(0);};
  const complete=()=>{stop();setStage('arrived');};
  const startDemo=()=>{
    if(!active)return;stop();setError('');setDemo(true);setStage('navigate');setProgress(0);setShade(statusByTimeFraction(active,0));
    setPosition(interpolateRoute(active,0)); let tick=0;
    interval.current=setInterval(()=>{
      tick++; const f=Math.min(1,tick/75);setProgress(f);setPosition(interpolateRoute(active,f));setShade(statusByTimeFraction(active,f));
      if(f>=1){clearInterval(interval.current!);interval.current=null;setStage('arrived');}
    },650);
  };
  const startGps=async()=>{
    if(!active)return;stop();setError('');
    try {
      const perm=await Location.requestForegroundPermissionsAsync();
      if(!perm.granted){setError('Location permission denied. Use Demo Walk instead.');return;}
      setDemo(false);setStage('navigate');
      subscription.current=await Location.watchPositionAsync({accuracy:Location.Accuracy.BestForNavigation,timeInterval:1000,distanceInterval:2}, sample=>{
        const coord:Coordinate=[sample.coords.longitude,sample.coords.latitude];
        const match=locateOnRoute(active,coord,sample.coords.accuracy);
        setPosition(coord);setProgress(match.fraction);setShade(match.state);
        if(!match.offRoute && match.fraction>.97 && sample.coords.accuracy!==null && sample.coords.accuracy<=25){complete();}
      });
    } catch(e){setError(e instanceof Error?e.message:'GPS unavailable');setStage('compare');stop();}
  };
  const reset=()=>{stop();setStage('search');setRoutes(null);setPosition(null);setProgress(0);setShade('unknown');setError('');};

  const Button=({text,onPress,primary=true}:{text:string,onPress:()=>void,primary?:boolean})=><TouchableOpacity onPress={onPress} style={[styles.button,!primary&&styles.outline]}><Text style={[styles.buttonText,!primary&&styles.outlineText]}>{text}</Text></TouchableOpacity>;
  return <View style={styles.root}><StatusBar style="dark"/>
    <ShadyMap route={stage==='search'?null:active} position={position} navigating={stage==='navigate'}/>
    <SafeAreaView style={styles.safe} pointerEvents="box-none">
      <View style={styles.brand}><Text style={styles.brandText}>☀ Shady Business</Text><Text style={styles.subtitle}>UCLA walking routes</Text></View>
      <View style={styles.spacer}/>
      <View style={styles.panel}>
        {stage==='search'&&<>
          <Text style={styles.heading}>Where are you going?</Text>
          <Text style={styles.label}>From</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.pills}>
            {places.map(place=><TouchableOpacity key={place.id} style={[styles.pill,origin===place.id&&styles.activePill]} onPress={()=>setOrigin(place.id)}><Text style={origin===place.id?styles.activeText:styles.pillText}>{place.name}</Text></TouchableOpacity>)}
          </ScrollView>
          <Text style={styles.label}>To</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.pills}>
            {places.map(place=><TouchableOpacity key={place.id} style={[styles.pill,destination===place.id&&styles.activePill]} onPress={()=>setDestination(place.id)}><Text style={destination===place.id?styles.activeText:styles.pillText}>{place.name}</Text></TouchableOpacity>)}
          </ScrollView>
          <View style={styles.tempRow}><Text style={styles.label}>Temperature (manual)</Text><View style={styles.tempControls}>
            <TouchableOpacity style={styles.tempButton} onPress={()=>setTemp(v=>Math.max(-5,v-2))}><Text style={styles.tempLabel}>−</Text></TouchableOpacity>
            <Text style={styles.tempValue}>{Math.round(temp*9/5+32)}°F</Text>
            <TouchableOpacity style={styles.tempButton} onPress={()=>setTemp(v=>Math.min(55,v+2))}><Text style={styles.tempLabel}>+</Text></TouchableOpacity>
          </View></View>
          <Button text={loading?'Calculating…':'Find walking routes'} onPress={()=>{if(!loading)void calculate();}}/>
        </>}
        {stage==='compare'&&<>
          <Text style={styles.heading}>Choose your walk</Text>
          <Text style={styles.muted}>{routes?.conditions.shade_model==='unavailable'?'Shade data unavailable — routes may be identical.':'Modeled sunlight, not guaranteed real-time shade.'}</Text>
          {routes?.routes.map(route=><TouchableOpacity key={route.mode} onPress={()=>selected(route.mode)} style={[styles.routeRow,chosen===route.mode&&styles.selected]}>
            <View style={{flex:1}}><Text style={styles.routeName}>{routeName[route.mode]}{route.same_as?' · same path':''}</Text>
            <Text style={styles.muted}>{route.sun_seconds===null?'Sun exposure unknown':`${Math.round(route.sun_seconds/60)} min modeled sun`}</Text></View>
            <Text style={styles.routeTime}>{Math.ceil(route.duration_s/60)} min</Text></TouchableOpacity>)}
          <Button text="Start guided walk" onPress={()=>void startGps()}/>
          <Button text="Demo walk (no GPS)" primary={false} onPress={startDemo}/>
          <TouchableOpacity style={styles.link} onPress={reset}><Text style={styles.linkText}>Change destination</Text></TouchableOpacity>
        </>}
        {stage==='navigate'&&<>
          <Text style={styles.heading}>{demo?'Demo navigation':'Walking navigation'}</Text>
          <Text style={styles.bigStatus}>{statusText[shade]}</Text>
          <Text style={styles.muted}>{Math.floor(progress*100)}% of route · {Math.max(0,Math.ceil((active?.duration_s??0)*(1-progress)/60))} min remaining</Text>
          {shade==='unknown'&&<Text style={styles.muted}>Shade estimate unavailable or position uncertain.</Text>}
          <Button text="End navigation" primary={false} onPress={()=>{stop();setStage('compare');setPosition(null);}}/>
        </>}
        {stage==='arrived'&&<><Text style={styles.heading}>You've arrived ✓</Text><Text style={styles.muted}>{demo?'Demonstration completed.':'Destination reached.'}</Text><Button text="Plan another walk" onPress={reset}/></>}
        {!!error&&<Text style={styles.error}>{error}</Text>}
        <Text style={styles.footer}>🟩 shade   🟧 sun   ⬛ unknown · Estimates only</Text>
      </View>
    </SafeAreaView>
  </View>;
}
const styles=StyleSheet.create({
  root:{flex:1,backgroundColor:'#E3EDE6'},safe:{flex:1},spacer:{flex:1},
  brand:{alignSelf:'flex-start',marginTop:12,marginLeft:18,padding:12,borderRadius:15,backgroundColor:'#FFF',elevation:4},
  brandText:{fontWeight:'800',fontSize:18,color:COLORS.ink},subtitle:{fontSize:11,color:'#64776A'},
  panel:{backgroundColor:'#FFF',paddingHorizontal:20,paddingTop:18,paddingBottom:24,borderTopLeftRadius:28,borderTopRightRadius:28,elevation:12},
  heading:{fontSize:21,fontWeight:'800',color:COLORS.ink,marginBottom:8},label:{fontWeight:'700',color:COLORS.ink,marginBottom:7,marginTop:9},
  pills:{flexGrow:0,maxHeight:43,marginBottom:4},pill:{borderRadius:21,backgroundColor:'#EDF2EE',padding:12,marginRight:7},
  activePill:{backgroundColor:COLORS.green},pillText:{color:COLORS.ink,fontSize:12},activeText:{color:'#FFF',fontWeight:'700',fontSize:12},
  tempRow:{flexDirection:'row',alignItems:'center',justifyContent:'space-between',marginTop:6,marginBottom:13},
  tempControls:{flexDirection:'row',alignItems:'center',gap:10},tempButton:{width:30,height:30,borderRadius:15,backgroundColor:'#EDF2EE',alignItems:'center',justifyContent:'center'},tempLabel:{fontSize:21,color:COLORS.green},tempValue:{fontSize:16,fontWeight:'700'},
  button:{backgroundColor:COLORS.green,paddingVertical:13,borderRadius:13,alignItems:'center',marginTop:7},buttonText:{color:'#FFF',fontSize:15,fontWeight:'700'},
  outline:{backgroundColor:'#F2F6F2'},outlineText:{color:COLORS.green},
  muted:{color:'#60736C',fontSize:12,lineHeight:18},routeRow:{flexDirection:'row',alignItems:'center',borderWidth:1,borderColor:'#EBEFEC',borderRadius:13,padding:11,marginTop:8},
  selected:{borderColor:COLORS.green,backgroundColor:'#F0F8F3'},routeName:{color:COLORS.ink,fontWeight:'700'},routeTime:{fontSize:17,fontWeight:'800',color:COLORS.ink},
  link:{alignSelf:'center',padding:8},linkText:{color:COLORS.green,fontWeight:'600'},bigStatus:{fontSize:27,fontWeight:'800',color:COLORS.green,marginVertical:9},
  error:{color:'#A53030',fontSize:12,marginTop:9},footer:{color:'#8A948C',fontSize:10,marginTop:10,textAlign:'center'}
});
