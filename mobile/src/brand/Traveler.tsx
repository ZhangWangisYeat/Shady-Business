import { useEffect, useRef, useState } from 'react';
import { Animated, Easing, Image, StyleSheet, View } from 'react-native';

const LOGO = require('./logo-intro.png');
// made by scripts/make_walk_sprites.py. going up the screen he has his back to
// you, coming down he faces you, and each way has its own jump frames: stand,
// crouch, deep crouch, spring, tuck. the jump out plays them forward and the
// landing plays them backward.
const SHEETS = {
  back: { walk: require('./walk-back.png'), jump: require('./jump-back.png') },
  front: { walk: require('./walk-front.png'), jump: require('./jump-front.png') },
};
const WALK_FRAMES = 8;
const JUMP_FRAMES = 5;
const FRAME_MS = 95;

// how the trip feels. he's this big while he's up and walking, whatever size
// the logo is at either end
const WALK_SIZE = 76;
// how far he stands up out of the screen. 0 is flat like the printed logo, and
// at 90 we'd be looking straight down on his head. somewhere in between reads as
// a little figure standing on the phone, seen from above the way you hold it.
const STAND_DEG = 58;
const CROUCH_MS = 260;
const AIR_MS = 400;
const HOP_PX = 30;
const SPEED_PX_PER_S = 360;

export type Spot = { x: number; y: number; size: number };

type Props = { from: Spot; to: Spot; onDone: () => void };

// one sprite sheet behind a one-frame window. the strip's offset is a stepped
// interpolation of `frame` (flat across each frame, then a jump), like css
// steps(), and it runs on the native driver
function Sheet({ source, frames, frame, visible }: { source: number; frames: number; frame: Animated.Value; visible: boolean }) {
  const input: number[] = [];
  const output: number[] = [];
  for (let i = 0; i < frames; i++) {
    input.push(i, i + 0.999);
    output.push(-i * WALK_SIZE, -i * WALK_SIZE);
  }
  return (
    <View style={[styles.window, { opacity: visible ? 1 : 0 }]}>
      <Animated.Image source={source} fadeDuration={0}
        style={{ width: WALK_SIZE * frames, height: WALK_SIZE, transform: [{ translateX: frame.interpolate({ inputRange: input, outputRange: output, extrapolate: 'clamp' }) }] }} />
    </View>
  );
}

// the logo crouches, springs up out of the screen and stands on it like the
// glass is the floor, walks over the map to the other spot (back to you going
// up, facing you coming down), then hops back in, lands in a crouch and lies flat
// again. everything runs on the native driver, so it stays smooth while the app
// is busy (the keyboard opening, a route loading).
export function Traveler({ from, to, onDone }: Props) {
  const start = { x: from.x + from.size / 2, y: from.y + from.size };
  const end = { x: to.x + to.size / 2, y: to.y + to.size };
  const view = end.y < start.y ? SHEETS.back : SHEETS.front;
  // feet position: he pivots and stands on the bottom middle of the logo
  const feet = useRef(new Animated.ValueXY(start)).current;
  const stand = useRef(new Animated.Value(0)).current;
  const hop = useRef(new Animated.Value(0)).current;
  const size = useRef(new Animated.Value(from.size / WALK_SIZE)).current;
  const cycle = useRef(new Animated.Value(0)).current;
  const jumpFrame = useRef(new Animated.Value(0)).current;
  const [mode, setMode] = useState<'flat' | 'jump' | 'walk'>('flat');

  useEffect(() => {
    const native = { useNativeDriver: true };
    const timing = (value: Animated.Value, toValue: number, duration: number, easing = Easing.linear) =>
      Animated.timing(value, { toValue, duration, easing, ...native });
    // the hop: up fast, down slower, with gravity-ish easing both ways
    const arc = () => Animated.sequence([
      timing(hop, 1, AIR_MS * 0.45, Easing.out(Easing.quad)),
      timing(hop, 0, AIR_MS * 0.55, Easing.in(Easing.quad)),
    ]);
    const jumpOut = Animated.sequence([
      // he bends down first, gathering himself, already starting to peel up off the glass
      Animated.parallel([
        timing(jumpFrame, 2.999, CROUCH_MS),
        timing(stand, 0.2, CROUCH_MS, Easing.out(Easing.quad)),
      ]),
      // then springs: stretched on the way up, tucked at the top, standing when he lands
      Animated.parallel([
        arc(),
        Animated.sequence([timing(jumpFrame, 3, 1), timing(jumpFrame, 4.999, AIR_MS * 0.5), timing(jumpFrame, 4.999, AIR_MS * 0.4), timing(jumpFrame, 0, 1)]),
        timing(stand, 1, AIR_MS, Easing.out(Easing.back(1.3))),
        timing(size, 1, AIR_MS, Easing.inOut(Easing.quad)),
      ]),
    ]);
    const jumpIn = Animated.sequence([
      // up off the floor tucked, then stretched toward the glass as he drops in
      Animated.parallel([
        arc(),
        Animated.sequence([timing(jumpFrame, 4, 1), timing(jumpFrame, 4.999, AIR_MS * 0.4), timing(jumpFrame, 3, 1), timing(jumpFrame, 3.999, AIR_MS * 0.5), timing(jumpFrame, 2.999, 1)]),
        timing(stand, 0.2, AIR_MS, Easing.in(Easing.quad)),
        timing(size, to.size / WALK_SIZE, AIR_MS + CROUCH_MS, Easing.inOut(Easing.quad)),
      ]),
      // and lands in a crouch that straightens out as he lies back down flat
      Animated.parallel([
        timing(jumpFrame, 0, CROUCH_MS),
        timing(stand, 0, CROUCH_MS, Easing.out(Easing.quad)),
      ]),
    ]);
    const distance = Math.hypot(end.x - start.x, end.y - start.y);
    const steps = Animated.loop(timing(cycle, WALK_FRAMES, WALK_FRAMES * FRAME_MS));
    let stopped = false;
    setMode('jump');
    jumpOut.start(({ finished }) => {
      if (!finished || stopped) return;
      setMode('walk');
      steps.start();
      // an even pace like a real walk; an ease reads as sliding on ice
      Animated.timing(feet, { toValue: end, duration: Math.max(700, (distance / SPEED_PX_PER_S) * 1000), easing: Easing.linear, ...native })
        .start(({ finished: walked }) => {
          if (!walked || stopped) return;
          steps.stop();
          setMode('jump');
          jumpIn.start(({ finished: landed }) => {
            if (!landed || stopped) return;
            setMode('flat');
            onDone();
          });
        });
    });
    return () => { stopped = true; steps.stop(); jumpOut.stop(); jumpIn.stop(); };
  }, []);

  const lift = hop.interpolate({ inputRange: [0, 1], outputRange: [0, -HOP_PX] });
  return (
    // above the elevated search card and sheet, which android otherwise draws over him
    <View style={[StyleSheet.absoluteFill, styles.layer]} pointerEvents="none">
      {/* his shadow stays on the floor while he hops, and only exists while he's up */}
      <Animated.View style={[styles.shadow, {
        opacity: Animated.multiply(stand, hop.interpolate({ inputRange: [0, 1], outputRange: [0.22, 0.1] })),
        transform: [
          { translateX: Animated.add(feet.x, -WALK_SIZE * 0.3) },
          { translateY: Animated.add(feet.y, -5) },
          { scale: Animated.multiply(size, hop.interpolate({ inputRange: [0, 1], outputRange: [1, 0.7] })) },
        ],
      }]} />
      {/* he pivots on his feet, so standing up and shrinking keep them planted.
          transformOrigin was ignored here (he turned around his middle and the
          shadow ended up at his knees), so instead he sits in the top half of a
          box twice his height: its center, the default pivot, is his feet. */}
      <Animated.View style={{
        position: 'absolute', left: 0, top: 0, width: WALK_SIZE, height: WALK_SIZE * 2,
        transform: [
          { translateX: Animated.add(feet.x, -WALK_SIZE / 2) },
          { translateY: Animated.add(Animated.add(feet.y, -WALK_SIZE), lift) },
          { perspective: 700 },
          { rotateX: stand.interpolate({ inputRange: [0, 1], outputRange: ['0deg', `-${STAND_DEG}deg`] }) },
          { scale: size },
        ],
      }}>
        {/* every sheet stays mounted (android fades an image in the first time it
            shows, which made him blink) and only the current one is visible */}
        <Sheet source={view.jump} frames={JUMP_FRAMES} frame={jumpFrame} visible={mode === 'jump'} />
        <View style={styles.overlay}><Sheet source={view.walk} frames={WALK_FRAMES} frame={cycle} visible={mode === 'walk'} /></View>
        <Image source={LOGO} fadeDuration={0} style={[styles.window, styles.overlay, { opacity: mode === 'flat' ? 1 : 0 }]} />
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  layer: { zIndex: 90, elevation: 90 },
  window: { width: WALK_SIZE, height: WALK_SIZE, overflow: 'hidden' },
  overlay: { position: 'absolute', top: 0, left: 0 },
  shadow: { position: 'absolute', left: 0, top: 0, width: WALK_SIZE * 0.6, height: 10, borderRadius: 5, backgroundColor: '#000' },
});
