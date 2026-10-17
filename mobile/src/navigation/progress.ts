import type { Coordinate, Route, ShadeState } from '../api/types';

function meters(a: Coordinate, b: Coordinate): number {
  const mid = (a[1] + b[1]) * Math.PI / 360;
  return Math.hypot((a[1]-b[1])*111320,(a[0]-b[0])*111320*Math.cos(mid));
}

export function interpolateRoute(route: Route, fraction: number): Coordinate {
  const points=route.geometry.coordinates;
  if (points.length < 2) return points[0];
  const distances=points.slice(1).map((p,i)=>meters(points[i],p));
  const total=distances.reduce((sum,n)=>sum+n,0);
  let remaining=Math.max(0,Math.min(1,fraction))*total;
  for (let i=0;i<distances.length;i++) {
    if (remaining <= distances[i]) {
      const t = distances[i] ? remaining/distances[i] : 0;
      return [points[i][0]+(points[i+1][0]-points[i][0])*t,
              points[i][1]+(points[i+1][1]-points[i][1])*t];
    }
    remaining-=distances[i];
  }
  return points[points.length-1];
}

export function statusByTimeFraction(route: Route, f: number): ShadeState {
  let current=0;
  const target=Math.max(0,Math.min(1,f))*route.duration_s;
  for (const segment of route.segments) {
    current+=segment.duration_s;
    if (target <= current) return segment.shade_state;
  }
  return 'unknown';
}

/** MVP GPS estimate: project onto sampled polyline and reject distant/low-quality fixes.
    Needs smoothing and direction/progress hysteresis before field deployment. */
export function locateOnRoute(route: Route, coord: Coordinate, accuracyM: number | null): { fraction: number; offRoute: boolean; state: ShadeState } {
  if (accuracyM == null || accuracyM > 30) return { fraction: 0, offRoute: true, state: 'unknown' };
  const pts=route.geometry.coordinates;
  const distances=pts.slice(1).map((p,i)=>meters(pts[i],p));
  const total=distances.reduce((a,b)=>a+b,0);
  let best={distance:Infinity,along:0}; let traveled=0;
  for (let i=0;i<distances.length;i++) {
    const x=pts[i],y=pts[i+1];
    const mid=Math.cos((x[1]+y[1])*Math.PI/360);
    const ax=(y[0]-x[0])*mid, ay=y[1]-x[1];
    const bx=(coord[0]-x[0])*mid, by=coord[1]-x[1];
    const dot=ax*ax+ay*ay;
    const t=dot ? Math.max(0,Math.min(1,(bx*ax+by*ay)/dot)) : 0;
    const projected: Coordinate=[x[0]+(y[0]-x[0])*t,x[1]+(y[1]-x[1])*t];
    const d=meters(projected,coord);
    if (d<best.distance) best={distance:d,along:traveled+distances[i]*t};
    traveled+=distances[i];
  }
  const fraction = total ? best.along/total : 0;
  const offRoute=best.distance>Math.max(25,accuracyM*1.5);
  return { fraction, offRoute, state: offRoute?'unknown':statusByTimeFraction(route,fraction) };
}
