jest.mock('expo-location', () => ({ watchHeadingAsync: jest.fn() }));
import { angleDelta, easeAngle } from '../src/location/heading';
import { glideLeft, glidePoint, nextGlide } from '../src/map/glide';

test('the heading eases the short way round north', () => {
  // 350 -> 10 should pass through 0, not swing back through 180
  const step = easeAngle(350, 10, 0.5);
  expect(step).toBeCloseTo(0);
  expect(angleDelta(350, 10)).toBe(20);
});

test('the heading settles on the reading even after readings stop', () => {
  // android goes quiet once you stop turning, so repeated ticks toward the last
  // reading have to get all the way there on their own
  let shown = 0;
  for (let i = 0; i < 40; i++) shown = easeAngle(shown, 90);
  expect(Math.abs(angleDelta(shown, 90))).toBeLessThan(0.5);
});

test('one jittery reading only nudges the heading', () => {
  expect(Math.abs(angleDelta(90, easeAngle(90, 100)))).toBeLessThan(2);
});

const A: [number, number] = [-118.4440, 34.0700];
const B: [number, number] = [-118.4439, 34.0700]; // about 9 m east

test('the dot glides from where it is to the next fix over the time between fixes', () => {
  const first = nextGlide(null, A, 0);
  const second = nextGlide(first, B, 1000);
  expect(second.duration).toBe(1000);
  expect(glidePoint(second, 1500)[0]).toBeCloseTo((A[0] + B[0]) / 2, 7);
  expect(glidePoint(second, 2000)).toEqual(B);
  expect(glideLeft(second, 1250)).toBe(750);
});

test('a fix that lands mid-glide carries on from where the dot is, not from the last fix', () => {
  const moving = { from: A, to: B, start: 0, duration: 1000 };
  const next = nextGlide(moving, A, 500);
  expect(next.from[0]).toBeCloseTo((A[0] + B[0]) / 2, 7);
});

test('a big jump teleports instead of sliding across campus', () => {
  const far: [number, number] = [-118.4400, 34.0700];
  const next = nextGlide(nextGlide(null, A, 0), far, 1000);
  expect(next.from).toEqual(far);
});
