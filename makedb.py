import contextlib
import datetime
import json
import math
import os
import os.path as path
import wave

import numpy
import py7zr
import pyworld as world
import soundfile

import pyutau

quant_strength = 60
db_name = "Unnamed"
lang = "Japanese"
pps = 200


def quantize(x, intensity):
    return int(round(x / intensity)) * intensity


def hz_to_midi(x):
    x = max(x, 55)
    note = 12 * (math.log2(x / 440))
    return int(round(note + 69))


def base_frq(f0, f0_min=55, f0_max=1760, outliers=0.2, trim=0.2):
    # Trim start and end to hopefully avoid pitch transitions
    f0 = f0[int(len(f0)*trim):-int(len(f0)*trim)]

    # Adjust min and max to ignore outliers
    sorted_f0 = f0.copy()
    sorted_f0.sort()

    if f0_min < sorted_f0[int(len(sorted_f0)*outliers)]:
        f0_min = sorted_f0[int(len(sorted_f0)*outliers)]
    if f0_max > sorted_f0[-int(len(sorted_f0)*outliers)]:
        f0_max = sorted_f0[-int(len(sorted_f0)*outliers)]

    f0 = f0[(f0 >= f0_min) & (f0 <= f0_max)]

    if len(f0) == 0:
        return float(f0_min)

    # Copied from https://github.com/titinko/frq0003gen/blob/master/src/frq0003gen.cpp
    value = 0
    r = 1
    p = [0, 0, 0, 0, 0, 0]
    q = 0
    avg_frq = 0
    base_value = 0
    for i in range(len(f0)):
        value = f0[i]
        if value < f0_max and value > f0_min:
            r = 1

            for j in range(6):
                if i > j:
                    q = f0[i - j - 1] - value
                    p[j] = value / (value + q * q)
                else:
                    p[j] = 1 / (1 + value)

                r *= p[j]

            avg_frq += value * r
            base_value += r

    if base_value > 0:
        avg_frq /= base_value
    return avg_frq


def estimate_pitch(audio_path, f0_min=55, f0_max=1760, pps=10):
    sf, sr = soundfile.read(audio_path)

    f0 = world.harvest(sf, sr, f0_min, f0_max, 1000/pps)

    return f0


base_wav = "WAV"
base_pit = "PIT"
base_ust = "UST"
base_lab = "LAB"
tempo_file = "tempos.txt"
flags_file = "flags.txt"
languages = None

for p in (base_wav, base_pit, base_ust, base_lab):
    if not path.exists(p):
        os.mkdir(p)

for f in (tempo_file, flags_file):
    if not path.exists(f):
        open(f, 'a').close()


with open('languages.json', encoding='utf-8') as l:
    languages = json.load(l)

tempos = {}
with open(tempo_file, encoding='utf-8') as p:
    for line in p:
        l = line.strip()
        if l.startswith("#") or l == "":
            continue
        l = l.split(' ')
        tempos[l[0]] = l[1]

flags = {}
with open(flags_file, encoding='utf-8') as p:
    for line in p:
        l = line.strip()
        if l.startswith("#") or l == "":
            continue
        l = l.split(' ')
        flags[l[0]] = l[1]

LABs = []

# Find all labs
for p in os.listdir(base_lab):
    if p.endswith(".lab"):
        LABs.append(p)


to_compress = []
errors = False
num_labels = 0
num_notes = 0
num_songs = 0
num_wavs_seconds = 0.0
num_pau_seconds = 0.0

for lab_file in LABs:
    print("Processing {}".format(lab_file))
    ust = pyutau.UtauPlugin.new_empty()

    try:
        ust.settings['Tempo'] = tempos[lab_file[:-4]]
    except KeyError:
        print("Tempo MISSING")
        continue

    lab_loc = path.join(base_lab, lab_file)
    pit_loc = path.join(base_pit, lab_file[:-4] + ".npy")
    wav_loc = path.join(base_wav, lab_file[:-4] + ".wav")
    ust_loc = path.join(base_ust, lab_file[:-4] + ".ust")

    print("Reading LAB")
    lab = open(lab_loc).readlines()
    phonemes = []
    duration = []
    pitches = []
    ups = 480 * float(ust.settings['Tempo']) / 60

    # Save phonemes in duration in list. Convert durations to note lengths
    for i in lab:
        ph = i.strip().split()
        length = (float(ph[1]) - float(ph[0])) / (10 ** 7)
        phonemes.append(ph[2])
        duration.append(ups * length)
        if ph[2] in ('pau', 'sil'):
            num_pau_seconds += length

    this_num_labels = len(phonemes)

    # Load or generate PIT
    frq = []
    if(os.path.exists(pit_loc)):
        print('Loading cached pitch...')
        frq = numpy.load(pit_loc)
    else:
        print('Estimating pitch...')
        frq, _ = estimate_pitch(wav_loc, pps=pps)
        numpy.save(pit_loc, frq)

    print('Generating ust...')
    # Fuse CVs
    for i in range(len(duration) - 1, -1, -1):
        if phonemes[i] not in languages[lang]['phonemes']:
            print("Warning: Bad phoneme {} at {}".format(
                phonemes[i], i+1))
            errors = True
        if phonemes[i][0] not in languages[lang]['vowels']:
            if phonemes[i] in languages[lang]['standalone']:
                continue
            else:
                if phonemes[i+1][0] in languages[lang]['vowels']:
                    np = phonemes[i] + phonemes[i+1]
                    if 'conversions' in languages[lang]:
                        if np not in languages[lang]['conversions']:
                            print("Waring, unknown lyric: {} at position {}".format(
                                note.lyric, i+1))
                            errors = True
                    phonemes[i+1] = np
                    duration[i-1] += duration[i]
                    del duration[i]
                    del phonemes[i]

    start = 0
    for i in range(len(duration)):
        length = duration[i] / ups
        end = start + length
        i_start = int(round(start * pps))
        i_end = int(round(end * pps))
        pitch = hz_to_midi(base_frq(frq[i_start:i_end]))
        pitches.append(pitch)
        start = end

    # Compensate duration for decimal to integer
    for i in range(len(duration) - 1):
        int_dur = int(duration[i])
        error = duration[i] - int_dur
        duration[i] = int_dur
        duration[i+1] += error

    duration[-1] = int(duration[-1])
    # Compensate duration for UTAU note lower limit
    for i in range(len(duration) - 1, -1, -1):
        if duration[i] < 15:
            error = 15 - duration[i]
            duration[i-1] -= error
            duration[i] = 15

    for i in range(0, len(duration) - 1):
        quant_dur = quantize(duration[i], quant_strength)
        error = duration[i] - quant_dur
        duration[i] = quant_dur
        duration[i+1] += error

    duration[-1] = quantize(duration[-1], quant_strength)

    for i in range(0, len(duration)):
        note = pyutau.create_note(phonemes[i] if phonemes[i] not in
                                  languages[lang]['silences'] else 'R', duration[i], note_num=pitches[i])
        note.note_type = "{:04d}".format(i)
        if note.lyric == 'R':
            note.note_num = 60
        else:
            if 'conversions' in languages[lang]:
                try:
                    note.lyric = languages[lang]['conversions'][note.lyric]
                except KeyError:
                    print("Waring, unknown lyric: {} at position {}".format(
                        note.lyric, i))
                    errors = True

        try:
            note.set_custom_data("Flags", flags[lab_file[:-4]])
        except KeyError:
            pass
        ust.notes.append(note)

    ust.write(ust_loc, withHeader=True)

    to_compress.extend([ust_loc, lab_loc, wav_loc])

    num_labels += this_num_labels
    num_notes += len(duration)
    num_songs += 1

    with contextlib.closing(wave.open(wav_loc, 'r')) as f:
        num_wavs_seconds += f.getnframes() / float(f.getframerate())

len_dataset = datetime.timedelta(seconds=round(num_wavs_seconds))
len_pau = datetime.timedelta(seconds=round(num_pau_seconds))
len_sound = len_dataset - len_pau

print("\n\nSTATISTICS:\nSongs: {}\nLabels: {}\nNotes: {}\nTotal duration: {}\nSilence: {}\nAudio: {}\n\n".format(
    num_songs, num_labels, num_notes, len_dataset, len_pau, len_sound))

if not errors:
    print("Creating archive...")
    filters = [{'id': py7zr.FILTER_DELTA}, {
        'id': py7zr.FILTER_LZMA2, 'preset': py7zr.PRESET_DEFAULT}]

    with py7zr.SevenZipFile(db_name+'.7z', 'w', filters=filters) as archive:
        for f in to_compress:
            print("Adding {}".format(f))
            archive.write(f)
