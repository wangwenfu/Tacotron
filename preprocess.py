from __future__ import print_function
from __future__ import division

import tensorflow as tf
import numpy as np
import os
import glob
import pickle as pkl
from tqdm import tqdm
import sys
import string

import audio
import argparse

mini = False
DATA_DIR = 'data/'

vocab = {}
ivocab = {}
vocab['<pad>'] = 0
ivocab[0] = '<pad>'

def save_vocab(name):
    global vocab
    global ivocab
    print('saving vocab')
    with open('data/%s/meta.pkl' % name, 'wb') as vf:
        pkl.dump({'vocab': ivocab, 'r': audio.r}, vf)

    vocab = {}
    ivocab = {}
    vocab['<pad>'] = 0
    ivocab[0] = '<pad>'

def process_char(char):
    if not char in vocab:
        next_index = len(vocab)
        vocab[char] = next_index
        ivocab[next_index] = char
    return vocab[char]

def pad_to_dense(inputs):
    max_len = max(r.shape[0] for r in inputs)
    if len(inputs[0].shape) == 1:
        padded = [np.pad(inp, (0, max_len - inp.shape[0]), 'constant', constant_values=0) \
                        for i, inp in enumerate(inputs)]
    else:
        padded = [np.pad(inp, ((0, max_len - inp.shape[0]),(0,0)), 'constant', constant_values=0) \
                        for i, inp in enumerate(inputs)]
    padded = np.stack(padded)
    return padded

def save_to_npy(texts, text_lens, mels, stfts, speech_lens, filename):
    texts, mels, stfts = pad_to_dense(texts), pad_to_dense(mels), pad_to_dense(stfts)

    stft_mean = np.mean(stfts, axis=(0,1))
    stft_std = np.std(stfts, axis=(0,1))
    np.save('data/' + filename + '/stft_mean', stft_mean)
    np.save('data/' + filename + '/stft_std', stft_std)

    text_lens, speech_lens = np.array(text_lens), np.array(speech_lens)

    inputs = texts, text_lens, mels, stfts, speech_lens
    names = 'texts', 'text_lens', 'mels', 'stfts', 'speech_lens'
    names = ['data/' + filename + '/' + name for name in names]

    for name, inp in zip(names, inputs):
        print(name, inp.shape)
        np.save(name, inp, allow_pickle=False)

def preprocess_blizzard():

    num_examples = 9733
    blizz_dir = DATA_DIR + 'blizzard/train/segmented/' 
    txt_file = blizz_dir + 'prompts.gui'

    # pad out all these jagged arrays and store them in an h5py file
    texts = []
    text_lens = []
    mels = []
    stfts = []
    speech_lens = []

    with open(txt_file, 'r') as ttf:
        for step in tqdm(range(num_examples)):
            id = ttf.readline().strip()
            text = ttf.readline()
            if not text: break
            # ugly but readable and the performance is fine
            text = text.replace('@ ', '').replace('| ', '').replace('# ', '') 
            text = text.replace(' ,', ',').replace(' ;', ';').replace(' :', ':')
            text = text.replace(' .', '.').strip()
            text = [process_char(c) for c in list(text)]

            # now load wav file
            wav_file = blizz_dir + 'wavn/' + id + '.wav'
            mel, stft = audio.process_wav(wav_file, sr=16000)
            if mel.shape[0] < 70:
                texts.append(np.array(text))
                text_lens.append(len(text))
                mels.append(mel)
                stfts.append(stft)
                speech_lens.append(mel.shape[0])

            # skip over weird phoneme deconstruction
            if not ttf.readline(): break

    save_to_npy(texts, text_lens, mels, stfts, speech_lens, 'blizzard')

    save_vocab('blizzard')

def preprocess_nancy():

    num_examples = 12095
    nancy_dir = DATA_DIR + 'nancy/' 
    txt_file = nancy_dir + 'prompts.data'

    # pad out all these jagged arrays and store them in an h5py file
    texts = []
    text_lens = []
    mels = []
    stfts = []
    speech_lens = []

    with open(txt_file, 'r') as ttf:
        for line in tqdm(ttf, total=num_examples):
            id = line.split()[1]
            text = line[line.find('"')+1:line.rfind('"')-1]

            text = [process_char(c) for c in list(text)]

            # now load wav file
            wav_file = nancy_dir + 'wavn/' + id + '.wav'
            mel, stft = audio.process_wav(wav_file, sr=16000)
            if mel.shape[0] < 70:
                texts.append(np.array(text))
                text_lens.append(len(text))
                mels.append(mel)
                stfts.append(stft)
                speech_lens.append(mel.shape[0])

    save_to_npy(texts, text_lens, mels, stfts, speech_lens, 'nancy')

    # save vocabulary
    save_vocab('nancy')

def preprocess_arctic():
    proto_file = DATA_DIR + 'arctic/train.proto'

    # pad out all these jagged arrays and store them in an h5py file
    texts = []
    text_lens = []
    mels = []
    stfts = []
    speech_lens = []

    txt_file = DATA_DIR + 'arctic/etc/arctic.data'
    with open(txt_file, 'r') as tff:
        for line in tqdm(tff, total=1138):
            spl = line.split()
            id = spl[1]
            text = ' '.join(spl[2:-1])
            text = text[1:-1]
            text = [process_char(c) for c in list(text)]

            wav_file = DATA_DIR + 'arctic/wav/{}.wav'.format(id)

            mel, stft = audio.process_wav(wav_file, sr=16000)

            texts.append(np.array(text))
            text_lens.append(len(text))
            mels.append(mel)
            stfts.append(stft)
            speech_lens.append(mel.shape[0])

    save_to_npy(texts, text_lens, mels, stfts, speech_lens, 'arctic')

    # save vocabulary
    save_vocab('arctic')

def preprocess_vctk():
    # adapted from https://github.com/buriburisuri/speech-to-text-wavenet/blob/master/preprocess.py
    import pandas as pd

    if mini:
        proto_file = DATA_DIR + 'VCTK-Corpus/mini_train.proto'
    else:
        proto_file = DATA_DIR + 'VCTK-Corpus/train.proto'

    # set up TensorFlow proto
    with open(proto_file, 'w') as pf:
        writer = tf.python_io.TFRecordWriter(pf.name)

        # read label-info
        df = pd.read_table(DATA_DIR + 'VCTK-Corpus/speaker-info.txt', usecols=['ID'],
                           index_col=False, delim_whitespace=True)
        # read file IDs
        file_ids = []
        for d in [DATA_DIR + 'VCTK-Corpus/txt/p%d/' % uid for uid in df.ID.values]:
            file_ids.extend([f[-12:-4] for f in sorted(glob.glob(d + '*.txt'))])

        for i, f in tqdm(enumerate(file_ids), total=len(file_ids)):

            # wave file name
            wav_file = DATA_DIR + 'VCTK-Corpus/wav48/%s/' % f[:4] + f + '.wav'
            txt_file = DATA_DIR + 'VCTK-Corpus/txt/%s/' % f[:4] + f + '.txt'

            mel, stft = audio.process_wav(wav_file)

            with open(txt_file, 'r') as tff:
                text = tff.read().strip()
                text = [process_char(c) for c in list(text)]
                #TODO possibly normalize text here?
            
            speaker = f[1:4]
            if mini and i > 9: break
            if speaker != '225': break

            sequence = make_sequence_example(stft, mel, text, speaker)
            writer.write(sequence.SerializeToString())
        writer.close()


if __name__ == '__main__':

    # not used for now
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', '-d', type=str, default='all')
    args = parser.parse_args()

    preprocess_arctic()
    preprocess_nancy()


