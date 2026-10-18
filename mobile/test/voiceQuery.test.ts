import { parseVoiceQuery } from '../src/search/voiceQuery';

test('extracts both places and one-place requests without inventing a start', () => {
  expect(parseVoiceQuery('from Royce Hall to Ackerman Union')).toEqual({ origin: 'Royce Hall', destination: 'Ackerman Union' });
  expect(parseVoiceQuery('从 Royce Hall 到 Ackerman Union')).toEqual({ origin: 'Royce Hall', destination: 'Ackerman Union' });
  expect(parseVoiceQuery('take me to Powell Library')).toEqual({ origin: null, destination: 'Powell Library' });
  expect(parseVoiceQuery('  ')).toBeNull();
});
