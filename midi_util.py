import sys, os
import numpy as np
import midi

RANGE = 128

def round_tick(tick, time_step):
    return int(round(tick/float(time_step)) * time_step)

def ingest_notes(track, verbose=False):

    notes = { n: [] for n in range(RANGE) }
    current_tick = 0

    for msg in track:
        # ignore all end of track events
        if isinstance(msg, midi.EndOfTrackEvent):
            continue

        if msg.tick > 0: 
            current_tick += msg.tick

        # velocity of 0 is equivalent to note off, so treat as such
        if isinstance(msg, midi.NoteOnEvent) and msg.get_velocity() != 0:
            if len(notes[msg.get_pitch()]) > 0 and \
               len(notes[msg.get_pitch()][-1]) != 2:
                if verbose:
                    print "Warning: double NoteOn encountered, deleting the first"
                    print msg
            else:
                notes[msg.get_pitch()] += [[current_tick]]
        elif isinstance(msg, midi.NoteOffEvent) or \
            (isinstance(msg, midi.NoteOnEvent) and msg.get_velocity() == 0):
            # sanity check: no notes end without being started
            if len(notes[msg.get_pitch()][-1]) != 1:
                if verbose:
                    print "Warning: skipping NoteOff Event with no corresponding NoteOn"
                    print msg
            else: 
                notes[msg.get_pitch()][-1] += [current_tick]

    return notes, current_tick

def round_notes(notes, track_ticks, time_step, R=None, O=None):
    if not R:
        R = RANGE
    if not O:
        O = 0

    sequence = np.zeros((track_ticks/time_step, R))
    for note in notes:
        for (start, end) in notes[note]:
            if end - start > time_step/2:
                start_t = round_tick(start, time_step) / time_step
                end_t = round_tick(end, time_step) / time_step
                if start_t != end_t:
                    sequence[start_t:end_t, note - O] = 1

    return sequence

def parse_midi_to_sequence(input_filename, time_step, verbose=False):
    sequence = []
    pattern = midi.read_midifile(input_filename)

    if len(pattern) < 1:
        raise Exception("No pattern found in midi file")

    if verbose:
        print "Track resolution: {}".format(pattern.resolution)
        print "Number of tracks: {}".format(len(pattern))
        print "Time step: {}".format(time_step)

    # Track ingestion stage
    notes = { n: [] for n in range(RANGE) }
    track_ticks = 0
    for track in pattern:
        current_tick = 0
        for msg in track:
            # ignore all end of track events
            if isinstance(msg, midi.EndOfTrackEvent):
                continue

            if msg.tick > 0: 
                current_tick += msg.tick

            # velocity of 0 is equivalent to note off, so treat as such
            if isinstance(msg, midi.NoteOnEvent) and msg.get_velocity() != 0:
                if len(notes[msg.get_pitch()]) > 0 and \
                   len(notes[msg.get_pitch()][-1]) != 2:
                    if verbose:
                        print "Warning: double NoteOn encountered, deleting the first"
                        print msg
                else:
                    notes[msg.get_pitch()] += [[current_tick]]
            elif isinstance(msg, midi.NoteOffEvent) or \
                (isinstance(msg, midi.NoteOnEvent) and msg.get_velocity() == 0):
                # sanity check: no notes end without being started
                if len(notes[msg.get_pitch()][-1]) != 1:
                    if verbose:
                        print "Warning: skipping NoteOff Event with no corresponding NoteOn"
                        print msg
                else: 
                    notes[msg.get_pitch()][-1] += [current_tick]

        track_ticks = max(current_tick, track_ticks)

    track_ticks = round_tick(track_ticks, time_step)
    if verbose:
        print "Track ticks (rounded): {} ({} time steps)".format(track_ticks, track_ticks/time_step)

    sequence = round_notes(notes, track_ticks, time_step)

    return sequence

class MidiWriter(object):

    def __init__(self, verbose=False):
        self.verbose = verbose
        self.note_range = RANGE

    def note_off(self, val, tick):
        self.track.append(midi.NoteOffEvent(tick=tick, pitch=val))

    def note_on(self, val, tick):
        self.track.append(midi.NoteOnEvent(tick=tick, pitch=val, velocity=70))

    def dump_sequence_to_midi(self, sequence, output_filename, time_step, 
                              resolution):
        if self.verbose:
            print "Dumping sequence to MIDI file: {}".format(output_filename)
            print "Resolution: {}".format(resolution)
            print "Time Step: {}".format(time_step)

        pattern = midi.Pattern(resolution=resolution)
        self.track = midi.Track()

        # reshape to (SEQ_LENGTH X NUM_DIMS)
        sequence = np.reshape(sequence, [-1, self.note_range])

        time_steps = sequence.shape[0]
        if self.verbose:
            print "Total number of time steps: {}".format(time_steps)

        steps_passed = 1
        notes_on = { n: False for n in range(self.note_range) }
        for seq_idx in range(time_steps):
            notes = np.nonzero(sequence[seq_idx, :])[0].tolist()

            # this tick will only be assigned to first NoteOn/NoteOff in
            # this time_step
            tick = steps_passed * time_step

            # NoteOffEvents come first so they'll have the tick value
            # go through all notes that are currently on and see if any
            # turned off
            for n in notes_on:
                if notes_on[n] and n not in notes:
                    self.note_off(n, tick)
                    tick, steps_passed = 0, 0
                    notes_on[n] = False

            # Turn on any notes that weren't previously on
            for note in notes:
                if not notes_on[note]:
                    self.note_on(note, tick)
                    tick, steps_passed = 0, 0
                    notes_on[note] = True

            steps_passed += 1

        # flush out notes
        tick = steps_passed * time_step
        for n in notes_on:
            self.note_off(n, tick)
            tick = 0
            notes_on[n] = False

        pattern.append(self.track)
        midi.write_midifile(output_filename, pattern)

def chord_on(notes=[]):
    chord = np.zeros(RANGE, dtype=np.float32)
    for n in notes:
        chord[n] = 1.0
    return chord 

def cmaj():
    return chord_on((72, 76, 79))

def amin():
    return chord_on((72, 76, 81))

def fmaj():
    return chord_on((72, 77, 81))

def gmaj():
    return chord_on((74, 79, 83))

def i_vi_iv_v(n):
    return [cmaj(), amin(), fmaj(), gmaj()] * n

if __name__ == '__main__':
    test_name = 'data_samples/koopa_troopa_beach.mid'
    time_step = 64
    resolution = 1024

    seq = parse_midi_to_sequence(test_name, time_step)
    writer = MidiWriter() 
    writer.dump_sequence_to_midi(seq, 'data_samples/test.midi', time_step, resolution)
