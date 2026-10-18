import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, SafeAreaView, StyleSheet, Text, TouchableOpacity, View, ScrollView } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import * as Location from 'expo-location';
import { ShadyMap } from './src/map/ShadyMap';
import { RecentRoutes, savedConditions } from './src/components/RecentRoutes';
import { ApiError, getPlaces, getRoutes } from './src/api/client';
import type { Coordinate, Place, Route, RoutesResponse, SavedRoute, ShadeState } from './src/api/types';
import { interpolateRoute, locateOnRoute, statusByTimeFraction } from './src/navigation/progress';

const COLORS={ink:'#203329',green:'#17785D',background:'#FFFFFF'};
const routeName:Record<Route['mode'],string>={fastest:'Fastest',recommended:'Recommended',maximum_shade:'Most shade'};
const statusText:Record<ShadeState,string>={shade:'In shade',sun:'In direct sun',unknown:'Shade unknown'};

type Stage='search'|'compare'|'navigate'|'arrived';
type ErrorAction='retry-places'|'retry-routes'|'choose-location'|'demo';
type ErrorNotice={message:string;action?:ErrorAction};
type NavigationIssue='weak-gps'|'off-route'|null;

const locationErrors=new Set(['PLACE_NOT_FOUND','OUTSIDE_SERVICE_AREA','SAME_ENDPOINT','SNAP_TOO_FAR','NO_WALKABLE_PATH','INVALID_REQUEST']);

function notice(error: unknown, retryAction: ErrorAction, fallback: string): ErrorNotice {
  if (error instanceof ApiError) {
    if (error.retryable) return {message:error.message,action:retryAction};
    if (error.code==='PLACE_NOT_FOUND') return {message:error.message,action:'retry-places'};
    if (locationErrors.has(error.code)) return {message:error.message,action:'choose-location'};
    return {message:error.message};
  }
  return {message:fallback};
}

export default function App() {
  const [stage,setStage]=useState<Stage>('search');
  const [places,setPlaces]=useState<Place[]>([]);
  const [origin,setOrigin]=useState('royce-hall');
  const [destination,setDestination]=useState('ackerman-union');
  const [temp,setTemp]=useState(84.2);
  const [routes,setRoutes]=useState<RoutesResponse|null>(null);
  const [savedRoute,setSavedRoute]=useState<SavedRoute|null>(null);
  const [chosen,setChosen]=useState<Route['mode']>('recommended');
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState<ErrorNotice|null>(null);
  const [progress,setProgress]=useState(0);
  const [position,setPosition]=useState<Coordinate|null>(null);
  const [shade,setShade]=useState<ShadeState>('unknown');
  const [demo,setDemo]=useState(false);
  const [navigationIssue,setNavigationIssue]=useState<NavigationIssue>(null);
  const subscription=useRef<Location.LocationSubscription|null>(null);
  const interval=useRef<ReturnType<typeof setInterval>|null>(null);
  const routeRequest=useRef(0);
  const active=routes?.routes.find(r=>r.mode===chosen) ?? null;
  const stop=()=>{subscription.current?.remove();subscription.current=null; if(interval.current) clearInterval(interval.current);interval.current=null;};
  const loadPlaces=async()=>{
    setError(null);
    try {setPlaces((await getPlaces()).places);}
    catch(e){setError(notice(e,'retry-places','Could not load UCLA locations.'));}
  };
  useEffect(()=>{void loadPlaces();return ()=>{routeRequest.current++;stop();};},[]);

  const changeOrigin=(value:string)=>{routeRequest.current++;setLoading(false);setError(null);setOrigin(value);};
  const changeDestination=(value:string)=>{routeRequest.current++;setLoading(false);setError(null);setDestination(value);};
  const changeTemperature=(delta:number)=>{routeRequest.current++;setLoading(false);setError(null);setTemp(v=>Math.max(23,Math.min(131,v+delta)));};

  const calculate=async()=>{
    if(origin===destination){setError({message:'Choose different start and destination.',action:'choose-location'});return;}
    const request=++routeRequest.current;
    setLoading(true);setError(null);
    try {
      const response=await getRoutes(origin,destination,temp);
      if(request!==routeRequest.current)return;
      setRoutes(response);setSavedRoute(null);setChosen('recommended');setStage('compare');
    } catch(e){if(request===routeRequest.current)setError(notice(e,'retry-routes','Could not calculate route.'));}
    finally{if(request===routeRequest.current)setLoading(false);}
  };
  const openSavedRoute=(item:SavedRoute)=>{
    routeRequest.current++;stop();setLoading(false);setError(null);
    setOrigin(item.request.origin.place_id);setDestination(item.request.destination.place_id);
    setRoutes(item.result);setSavedRoute(item);setChosen('recommended');
    setPosition(null);setProgress(0);setShade('unknown');setNavigationIssue(null);setStage('compare');
  };
  const selected=(mode:Route['mode'])=>{setChosen(mode);setPosition(null);setProgress(0);};
  const complete=()=>{stop();setStage('arrived');};
  const startDemo=()=>{
    if(!active)return;routeRequest.current++;setLoading(false);stop();setError(null);setNavigationIssue(null);setDemo(true);setStage('navigate');setProgress(0);setShade(statusByTimeFraction(active,0));
    setPosition(interpolateRoute(active,0)); let tick=0;
    interval.current=setInterval(()=>{
      tick++; const f=Math.min(1,tick/75);setProgress(f);setPosition(interpolateRoute(active,f));setShade(statusByTimeFraction(active,f));
      if(f>=1){clearInterval(interval.current!);interval.current=null;setStage('arrived');}
    },650);
  };
  const startGps=async()=>{
    if(!active||savedRoute)return;stop();setError(null);setNavigationIssue(null);
    try {
      const perm=await Location.requestForegroundPermissionsAsync();
      if(!perm.granted){setError({message:'Location permission denied. Use Demo Walk instead.',action:'demo'});return;}
      setDemo(false);setStage('navigate');
      subscription.current=await Location.watchPositionAsync({accuracy:Location.Accuracy.BestForNavigation,timeInterval:1000,distanceInterval:2}, sample=>{
        const coord:Coordinate=[sample.coords.longitude,sample.coords.latitude];
        const match=locateOnRoute(active,coord,sample.coords.accuracy);
        const issue=sample.coords.accuracy===null||sample.coords.accuracy>30?'weak-gps':match.offRoute?'off-route':null;
        setNavigationIssue(issue);setPosition(coord);setShade(match.state);
        if(!match.offRoute)setProgress(match.fraction);
        if(!match.offRoute && match.fraction>.97 && sample.coords.accuracy!==null && sample.coords.accuracy<=25){complete();}
      });
    } catch{setError({message:'GPS is unavailable right now. Try again or use Demo Walk.',action:'demo'});setStage('compare');stop();}
  };
  const reset=()=>{routeRequest.current++;stop();setLoading(false);setStage('search');setRoutes(null);setSavedRoute(null);setPosition(null);setProgress(0);setShade('unknown');setNavigationIssue(null);setError(null);};

  const errorActionText=error?.action==='retry-places'?'Retry locations':error?.action==='retry-routes'?'Retry route':error?.action==='demo'?'Use Demo Walk':error?.action==='choose-location'?'Choose another location':null;
  const handleErrorAction=()=>{
    const action=error?.action;setError(null);
    if(action==='retry-places')void loadPlaces();
    else if(action==='retry-routes')void calculate();
    else if(action==='demo')startDemo();
    else if(action==='choose-location')setStage('search');
  };

  const Button=({text,onPress,primary=true}:{text:string,onPress:()=>void,primary?:boolean})=><TouchableOpacity accessibilityRole="button" onPress={onPress} style={[styles.button,!primary&&styles.outline]}><Text style={[styles.buttonText,!primary&&styles.outlineText]}>{text}</Text></TouchableOpacity>;
  return <View style={styles.root}><StatusBar style="dark"/>
    <ShadyMap route={stage==='search'?null:active} position={position} navigating={stage==='navigate'}/>
    <SafeAreaView style={styles.safe} pointerEvents="box-none">
      <View style={styles.brand}><Text style={styles.brandText}>☀ Shady Business</Text><Text style={styles.subtitle}>UCLA walking routes</Text></View>
      <View style={styles.spacer}/>
      <ScrollView style={styles.panel} contentContainerStyle={styles.panelContent} keyboardShouldPersistTaps="handled" nestedScrollEnabled>
        {stage==='search'&&<>
          <Text style={styles.heading}>Where are you going?</Text>
          <Text style={styles.label}>From</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.pills}>
            {places.map(place=><TouchableOpacity key={place.id} style={[styles.pill,origin===place.id&&styles.activePill]} onPress={()=>changeOrigin(place.id)}><Text style={origin===place.id?styles.activeText:styles.pillText}>{place.name}</Text></TouchableOpacity>)}
          </ScrollView>
          <Text style={styles.label}>To</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.pills}>
            {places.map(place=><TouchableOpacity key={place.id} style={[styles.pill,destination===place.id&&styles.activePill]} onPress={()=>changeDestination(place.id)}><Text style={destination===place.id?styles.activeText:styles.pillText}>{place.name}</Text></TouchableOpacity>)}
          </ScrollView>
          <RecentRoutes places={places} onSelect={openSavedRoute}/>
          <View style={styles.tempRow}><Text style={styles.label}>Temperature (manual)</Text><View style={styles.tempControls}>
            <TouchableOpacity style={styles.tempButton} onPress={()=>changeTemperature(-2)}><Text style={styles.tempLabel}>−</Text></TouchableOpacity>
            <Text style={styles.tempValue}>{Math.round(temp)}°F</Text>
            <TouchableOpacity style={styles.tempButton} onPress={()=>changeTemperature(2)}><Text style={styles.tempLabel}>+</Text></TouchableOpacity>
          </View></View>
          <Button text={loading?'Calculating…':'Find walking routes'} onPress={()=>{if(!loading)void calculate();}}/>
        </>}
        {stage==='compare'&&<>
          <Text style={styles.heading}>Choose your walk</Text>
          {savedRoute&&<View style={styles.historyNotice}>
            <Text style={styles.historyTitle}>Saved route · {savedConditions(savedRoute)}</Text>
            <Text style={styles.muted}>Historical shade estimate. Update for now before GPS guidance.</Text>
          </View>}
          <Text style={styles.muted}>{routes?.conditions.shade_model==='unavailable'?'Shade data unavailable — routes may be identical.':'Modeled sunlight, not guaranteed real-time shade.'}</Text>
          {routes?.routes.map(route=><TouchableOpacity key={route.mode} onPress={()=>selected(route.mode)} style={[styles.routeRow,chosen===route.mode&&styles.selected]}>
            <View style={{flex:1}}><Text style={styles.routeName}>{routeName[route.mode]}{route.same_as?' · same path':''}</Text>
            <Text style={styles.muted}>{route.sun_seconds===null?'Sun exposure unknown':`${Math.round(route.sun_seconds/60)} min modeled sun`}</Text></View>
            <Text style={styles.routeTime}>{Math.ceil(route.duration_s/60)} min</Text></TouchableOpacity>)}
          {savedRoute?<Button text={loading?'Updating…':'Update for guided walk'} onPress={()=>{if(!loading)void calculate();}}/>:
            <Button text="Start guided walk" onPress={()=>void startGps()}/>}
          <Button text="Demo walk (no GPS)" primary={false} onPress={startDemo}/>
          <TouchableOpacity style={styles.link} onPress={reset}><Text style={styles.linkText}>Change destination</Text></TouchableOpacity>
        </>}
        {stage==='navigate'&&<>
          <Text style={styles.heading}>{demo?'Demo navigation':'Walking navigation'}</Text>
          <Text style={styles.bigStatus}>{statusText[shade]}</Text>
          <Text style={styles.muted}>{Math.floor(progress*100)}% of route · {Math.max(0,Math.ceil((active?.duration_s??0)*(1-progress)/60))} min remaining</Text>
          {navigationIssue&&<Text accessibilityLiveRegion="polite" style={styles.warning}>{navigationIssue==='weak-gps'?'GPS signal is weak — shade status is unavailable.':'You appear to be off route. Return to the highlighted path.'}</Text>}
          {shade==='unknown'&&<Text style={styles.muted}>Shade estimate unavailable or position uncertain.</Text>}
          <Button text="End navigation" primary={false} onPress={()=>{stop();setStage('compare');setPosition(null);setNavigationIssue(null);}}/>
        </>}
        {stage==='arrived'&&<><Text style={styles.heading}>You've arrived ✓</Text><Text style={styles.muted}>{demo?'Demonstration completed.':'Destination reached.'}</Text><Button text="Plan another walk" onPress={reset}/></>}
        {error&&<View accessibilityLiveRegion="assertive" style={styles.errorCard}><Text style={styles.error}>{error.message}</Text>{errorActionText&&<TouchableOpacity accessibilityRole="button" onPress={handleErrorAction}><Text style={styles.errorAction}>{errorActionText}</Text></TouchableOpacity>}</View>}
        <Text style={styles.footer}>🟩 shade   🟧 sun   ⬛ unknown · Estimates only</Text>
      </ScrollView>
    </SafeAreaView>
  </View>;
}
const styles=StyleSheet.create({
  root:{flex:1,backgroundColor:'#E3EDE6'},safe:{flex:1},spacer:{flex:1},
  brand:{alignSelf:'flex-start',marginTop:12,marginLeft:18,padding:12,borderRadius:15,backgroundColor:'#FFF',elevation:4},
  brandText:{fontWeight:'800',fontSize:18,color:COLORS.ink},subtitle:{fontSize:11,color:'#64776A'},
  panel:{backgroundColor:'#FFF',flexGrow:0,maxHeight:'82%',borderTopLeftRadius:28,borderTopRightRadius:28,elevation:12},
  panelContent:{paddingHorizontal:20,paddingTop:18,paddingBottom:24},
  historyNotice:{backgroundColor:'#F2F6F2',borderRadius:13,padding:11,marginBottom:8},historyTitle:{color:COLORS.green,fontSize:12,fontWeight:'700',lineHeight:18,marginBottom:3},
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
  warning:{color:'#7A4B00',backgroundColor:'#FFF4D8',fontSize:12,lineHeight:18,padding:10,borderRadius:10,marginTop:8},
  errorCard:{backgroundColor:'#FFF0F0',borderRadius:10,padding:10,marginTop:9},error:{color:'#8E2525',fontSize:12,lineHeight:18},errorAction:{color:COLORS.green,fontWeight:'700',fontSize:12,marginTop:7},footer:{color:'#8A948C',fontSize:10,marginTop:10,textAlign:'center'}
});
