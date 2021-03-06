#! /usr/bin/env python

import tensorflow as tf
import numpy as np
import os
import time
import datetime
import eval_data_helpers
from word2vec_helpers import Word2VecHelper
import csv

# Parameters
# ==================================================

# Data Parameters
tf.flags.DEFINE_string("eval_data_file",        "../data/eval_data.txt", "Data source for the eval")

# Eval Parameters
tf.flags.DEFINE_integer("batch_size",           1,                      "Batch Size (default: 64)")
tf.flags.DEFINE_string("checkpoint_dir",        "runs/20170721103540",  "Checkpoint directory from training run")

# Misc Parameters
tf.flags.DEFINE_boolean("allow_soft_placement", True,                   "Allow device soft device placement")
tf.flags.DEFINE_boolean("log_device_placement", False,                  "Log placement of ops on devices")


FLAGS = tf.flags.FLAGS
FLAGS._parse_flags()
print("\nParameters:")
for attr, value in sorted(FLAGS.__flags.items()):
    print("{}={}".format(attr.upper(), value))
print("")

# Load data
eval_size, x_raw, y_test = eval_data_helpers.load_data(FLAGS.eval_data_file)

max_document_length = 22
word2vec_helpers = Word2VecHelper()
x_test = word2vec_helpers.SentencesIndex(x_raw, max_document_length)

# Checkpoint
ckpt = tf.train.get_checkpoint_state(os.path.join(FLAGS.checkpoint_dir, 'checkpoints'))
if ckpt:
    print("Read model parameters from %s" % ckpt.model_checkpoint_path)

# Evaluation
# ==================================================
print("\nEvaluating...\n")

graph = tf.Graph()
with graph.as_default():
    session_conf = tf.ConfigProto(
    allow_soft_placement=FLAGS.allow_soft_placement,
    log_device_placement=FLAGS.log_device_placement)
    session_conf.gpu_options.allow_growth = True
    sess = tf.Session(config=session_conf)
    with sess.as_default():
        # Load the saved meta graph and restore variables
        saver = tf.train.import_meta_graph("{}.meta".format(ckpt.model_checkpoint_path))
        saver.restore(sess, ckpt.model_checkpoint_path)

        # Get the placeholders from the graph by name
        input_x = graph.get_operation_by_name("input_x").outputs[0]
        dropout_keep_prob = graph.get_operation_by_name("dropout_keep_prob").outputs[0]
        batch_size = graph.get_operation_by_name("batch_size").outputs[0]
        real_len = graph.get_operation_by_name("real_len").outputs[0]

        def real_len_func(batches):
            return [np.argmin(batch + [0]) for batch in batches]

        # Tensors we want to evaluate
        prediction = graph.get_operation_by_name("output/predictions").outputs[0]
        score = graph.get_operation_by_name("output/scores").outputs[0]
        softmax = tf.nn.softmax(score)
        attention_weight = graph.get_operation_by_name("attention/attention_weights").outputs[0]
        
        # Collect the predictions here
        all_predictions = []
        all_scores = []
        all_softmax = []
        all_attentions = []
        for i in range(len(x_test)):
            real_len_value = real_len_func([x_test[i]])
            feed_dict = {
              input_x: [x_test[i]],
              dropout_keep_prob: 1.0,
              batch_size: 1,
              real_len: real_len_value
            }
            batch_attention, \
            batch_prediction, \
            batch_score, \
            batch_softmax = \
            sess.run([attention_weight, prediction, score, softmax], 
                feed_dict)

            all_attentions.append(batch_attention)
            all_predictions = np.concatenate([all_predictions, batch_prediction])
            all_scores.append(batch_score)
            all_softmax.append(batch_softmax)
            print(x_test[i])
            print(x_raw[i])
            print(batch_attention[0][0:real_len_value[0]])

# Print accuracy if y_test is defined
if y_test is not None:
    correct_predictions = float(sum(all_predictions == y_test))
    print("Total number of test examples: {}".format(len(y_test)))
    print("Accuracy: {:g}".format(correct_predictions/float(len(y_test))))

    for th in np.linspace(0,0.95,10):
        threshold = th
        true_pos = 0
        true_neg = 0
        false_pos = 0
        false_neg = 0
        for i in range(len(y_test)):
            if all_predictions[i] != 0:
                if all_softmax[i][0][int(all_predictions[i])] > threshold:
                    if all_predictions[i] == y_test[i]: 
                        true_pos += 1
                    if all_predictions[i] != y_test[i]:
                        false_pos += 1

        precision = true_pos / (true_pos + false_pos)
        print("Precision: {} in {} threshold".format(precision, threshold))

# Save the evaluation to a csv
predictions_human_readable = np.column_stack((np.array(x_raw), y_test, all_predictions))
out_path = os.path.join(FLAGS.checkpoint_dir, "..", "prediction.csv")
print("Saving evaluation to {0}".format(out_path))
with open(out_path, 'w') as f:
    csv.writer(f).writerows(predictions_human_readable)