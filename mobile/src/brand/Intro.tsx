import { useEffect, useRef, useState } from 'react';
import { Animated, Easing, Image, Pressable, StyleSheet, useWindowDimensions, View } from 'react-native';

const LOGO = require('./logo-intro.png');
const WORDMARK = require('./wordmark.png');
// 8 walking frames side by side, made by scripts/make_walk_sprites.py from the
// icon (same cloud, redrawn legs). they're stepped through like the resume
// site's player sheet: the strip slides one whole frame at a time behind a
// frame-sized window, the way css steps() jumps background-position.
const WALK_SHEET = require('./walk-sheet.png');
const FRAMES = 8;
const FRAME_MS = 95;
// the wordmark is the exact image from the brand files, so the letters are
// revealed by widening a clip over it. these are where each letter ends, as a
// share of the image width, measured from its inked columns. the y is listed
// twice so the space before "business" takes a beat like a typed space would.
// e, s and s touch in the artwork, so their split is the thinnest column between them.
const LETTER_ENDS = [0.073, 0.156, 0.243, 0.332, 0.422, 0.422, 0.532, 0.61, 0.677, 0.707, 0.789, 0.87, 0.93, 1];
const WORDMARK_RATIO = 823 / 125;
// matches the logo artwork's own background, so the big logo looks like it's
// printed on the page instead of sitting on a white square
export const INTRO_BACKGROUND = '#FEFEFE';
const ENTER_MS = 1500;
const LETTER_MS = 110;
const HOLD_MS = 650;
const LEAVE_MS = 900;

export type Target = { x: number; y: number; size: number };
type Phase = 'entering' | 'typing' | 'hold' | 'leaving';

type Props = {
  // where the small logo sits next to the search bars, in window coordinates.
  // it's asked for right before he leaves, because the card can move after launch
  measureTarget: () => Promise<Target | null>;
  onDone: () => void;
};

// the walking frames behind a window one frame wide. the strip's offset is a
// stepped interpolation (flat across each frame, then a jump), so the native
// driver can run it without a render per frame.
function WalkCycle({ size, cycle, onLoad }: { size: number; cycle: Animated.Value; onLoad: () => void }) {
  const input: number[] = [];
  const output: number[] = [];
  for (let i = 0; i < FRAMES; i++) {
    input.push(i, i + 0.999);
    output.push(-i * size, -i * size);
  }
  const offset = cycle.interpolate({ inputRange: input, outputRange: output });
  return (
    <View style={{ width: size, height: size, overflow: 'hidden' }}>
      <Animated.Image source={WALK_SHEET} fadeDuration={0} onLoad={onLoad} style={{ width: size * FRAMES, height: size, transform: [{ translateX: offset }] }} />
    </View>
  );
}

export function Intro({ measureTarget, onDone }: Props) {
  const { width, height } = useWindowDimensions();
  const [letters, setLetters] = useState(0);
  const [phase, setPhase] = useState<Phase>('entering');
  const enter = useRef(new Animated.Value(0)).current;
  const leave = useRef(new Animated.Value(0)).current;
  const cycle = useRef(new Animated.Value(0)).current;
  const [target, setTarget] = useState<Target | null>(null);
  // the walk-in waits until the sheet, the standing logo and the name have all
  // loaded. on launch the first run started before they were decoded, so he
  // walked in invisibly and then faded in standing in the middle.
  const [loaded, setLoaded] = useState(0);
  const ready = loaded >= 3;
  const onLoad = () => setLoaded(n => n + 1);
  // in case an image never reports back, he sets off anyway after a moment
  useEffect(() => { const timer = setTimeout(() => setLoaded(3), 1500); return () => clearTimeout(timer); }, []);

  const big = Math.min(width * 0.58, 300);
  const wordWidth = Math.min(width * 0.78, 420);
  const wordHeight = wordWidth / WORDMARK_RATIO;
  const logoTop = height * 0.5 - (big + 18 + wordHeight) / 2;
  const logoLeft = (width - big) / 2;
  // only the walk-in uses his legs. at the end he just glides down into his spot
  // (the user asked for that over a walk, for now)
  const walking = phase === 'entering';

  // his legs only move while he's going somewhere
  useEffect(() => {
    if (!walking) return;
    cycle.setValue(0);
    const steps = Animated.loop(Animated.timing(cycle, {
      toValue: FRAMES, duration: FRAMES * FRAME_MS, easing: Easing.linear, useNativeDriver: true,
    }));
    steps.start();
    return () => steps.stop();
  }, [walking]);

  // he walks in from off the left edge to the middle, at an even pace like a
  // real walk (an ease would look like he's sliding on ice)
  useEffect(() => {
    if (phase !== 'entering' || !ready) return;
    const run = Animated.timing(enter, { toValue: 1, duration: ENTER_MS, easing: Easing.linear, useNativeDriver: true });
    run.start(({ finished }) => { if (finished) setPhase('typing'); });
    return () => run.stop();
  }, [phase, ready]);

  // one letter at a time under him, then a short pause on the finished logo
  useEffect(() => {
    if (phase !== 'typing') return;
    if (letters >= LETTER_ENDS.length) { setPhase('hold'); return; }
    const timer = setTimeout(() => setLetters(n => n + 1), letters === 0 ? 250 : LETTER_MS);
    return () => clearTimeout(timer);
  }, [phase, letters]);

  useEffect(() => {
    if (phase !== 'hold') return;
    const timer = setTimeout(() => setPhase('leaving'), HOLD_MS);
    return () => clearTimeout(timer);
  }, [phase]);

  // then the logo shifts down into his spot next to "Where to?", shrinking as it goes
  useEffect(() => {
    if (phase !== 'leaving') return;
    let cancelled = false;
    void measureTarget().then(spot => {
      if (cancelled) return;
      setTarget(spot);
      Animated.timing(leave, { toValue: 1, duration: LEAVE_MS, easing: Easing.inOut(Easing.cubic), useNativeDriver: true })
        .start(() => onDone());
    });
    return () => { cancelled = true; };
  }, [phase]);

  // a tap while he walks in or while the text types jumps to him standing with
  // the whole name; a tap on the finished logo sends him off straight away. the
  // walk to the corner can't be cut short, because stopping halfway would leave
  // him floating over the map.
  const skip = () => {
    if (phase === 'entering' || phase === 'typing') {
      enter.stopAnimation();
      enter.setValue(1);
      setLetters(LETTER_ENDS.length);
      setPhase('hold');
    } else if (phase === 'hold') setPhase('leaving');
  };

  // without a measured spot he heads for the top right corner, which is where
  // the search card keeps him anyway
  const end = target ?? { x: width - 58, y: 60, size: 34 };
  const scale = end.size / big;
  // scaling happens around the center, so the translation is between centers
  const dx = end.x + end.size / 2 - (logoLeft + big / 2);
  const dy = end.y + end.size / 2 - (logoTop + big / 2);
  const fade = leave.interpolate({ inputRange: [0, 0.75, 1], outputRange: [1, 0.35, 0] });
  const shown = letters ? LETTER_ENDS[Math.min(letters, LETTER_ENDS.length) - 1] : 0;

  return (
    // the search card and sheet have android elevation, which draws them above
    // later siblings, so the intro needs a higher one to cover them
    <Pressable style={[StyleSheet.absoluteFill, styles.cover]} onPress={skip} accessibilityLabel="Shady Business. Tap to skip" accessibilityRole="button">
      <Animated.View style={[StyleSheet.absoluteFill, { backgroundColor: INTRO_BACKGROUND, opacity: fade }]} />
      <Animated.View style={[styles.word, { top: logoTop + big + 18, left: (width - wordWidth) / 2, width: wordWidth * shown, height: wordHeight, opacity: fade }]}>
        <Image source={WORDMARK} fadeDuration={0} onLoad={onLoad} style={{ width: wordWidth, height: wordHeight }} resizeMode="contain" />
      </Animated.View>
      <Animated.View style={{
        position: 'absolute', top: logoTop, left: logoLeft, width: big, height: big,
        transform: [
          { translateX: enter.interpolate({ inputRange: [0, 1], outputRange: [-(logoLeft + big), 0] }) },
          { translateX: leave.interpolate({ inputRange: [0, 1], outputRange: [0, dx] }) },
          { translateY: leave.interpolate({ inputRange: [0, 1], outputRange: [0, dy] }) },
          { scale: leave.interpolate({ inputRange: [0, 1], outputRange: [1, scale] }) },
        ],
      }}>
        {/* both stay mounted (android fades images in when they first appear,
            and swapping them in and out made him blink) and only one is shown. the
            standing one gets an explicit size, because stretched to fill it drew
            oversized for a couple of frames the first time it showed */}
        <View style={{ opacity: walking ? 1 : 0 }}><WalkCycle size={big} cycle={cycle} onLoad={onLoad} /></View>
        <Image source={LOGO} fadeDuration={0} onLoad={onLoad} style={{ position: 'absolute', top: 0, left: 0, width: big, height: big, opacity: walking ? 0 : 1 }} />
      </Animated.View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  cover: { zIndex: 100, elevation: 100 },
  word: { position: 'absolute', overflow: 'hidden' },
});
