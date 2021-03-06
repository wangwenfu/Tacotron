import tensorflow as tf
import numpy as np
import sys
import os
import data_input
import librosa

from tqdm import tqdm
import argparse

import audio

def test(model, config, prompt_file):

    meta = data_input.load_meta(config.data_path)
    assert config.r == meta['r']
    ivocab = meta['vocab']
    config.vocab_size = len(ivocab)

    with tf.device('/cpu:0'):
        batch_inputs, config.num_prompts = data_input.load_prompts(prompt_file, ivocab)

    with tf.Session() as sess:
        stft_mean, stft_std = \
                np.load(config.data_path + 'stft_mean.npy'), np.load(config.data_path + 'stft_std.npy')

        # initialize model
        model = model(config, batch_inputs, train=False)

        train_writer = tf.summary.FileWriter('log/' + config.save_path + '/test', sess.graph)

        tf.global_variables_initializer().run()
        tf.local_variables_initializer().run()
        coord = tf.train.Coordinator()
        threads = tf.train.start_queue_runners(sess=sess, coord=coord)

        saver = tf.train.Saver()

        print('restoring weights')
        latest_ckpt = tf.train.latest_checkpoint(
            'weights/' + config.save_path[:config.save_path.rfind('/')]
        )
        saver.restore(sess, latest_ckpt)

        try:
            while(True):
                out = sess.run([
                    model.output,
                    batch_inputs
                ])
                outputs, inputs = out

                print('saving samples')
                for out, words in zip(outputs, inputs['text']):
                    # store a sample to listen to
                    text = ''.join([ivocab[w] for w in words])
                    out *= stft_std
                    out += stft_mean
                    sample = audio.invert_spectrogram(out)
                    merged = sess.run(tf.summary.merge(
                         [tf.summary.audio(text, sample[None, :], 16000)]
                    ))
                    train_writer.add_summary(merged, 0)
        except tf.errors.OutOfRangeError:
            coord.request_stop()
            coord.join(threads)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('prompts')
    parser.add_argument('-t', '--train-set', default='nancy')
    args = parser.parse_args()

    from models.tacotron import Tacotron, Config
    model = Tacotron
    config = Config()
    config.data_path = 'data/%s/' % args.train_set
    config.save_path = args.train_set + '/tacotron'
    print('Buliding Tacotron')

    test(model, config, args.prompts)
