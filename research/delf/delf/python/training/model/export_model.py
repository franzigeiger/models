# Lint as: python3
# Copyright 2020 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Export DELF tensorflow inference model.

This model includes feature extraction, receptive field calculation and
key-point selection and outputs the selected feature descriptors.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os

from absl import app
from absl import flags
import tensorflow as tf

from delf.python.training.model import delf_model
from delf.python.training.model import export_model_utils

FLAGS = flags.FLAGS

flags.DEFINE_string('ckpt_path', '/tmp/delf-logdir/delf-weights',
                    'Path to saved checkpoint.')
flags.DEFINE_string('export_path', None, 'Path where model will be exported.')
flags.DEFINE_boolean('block3_strides', False,
                     'Whether to apply strides after block3.')
flags.DEFINE_float('iou', 1.0, 'IOU for non-max suppression.')


class _ExtractModule(tf.Module):
  """Helper module to build and save DELF model."""

  def __init__(self, block3_strides, iou):
    """Initialization of DELF model.

    Args:
      block3_strides: bool, whether to add strides to the output of block3.
      iou: IOU for non-max suppression.
    """
    self._stride_factor = 2.0 if block3_strides else 1.0
    self._iou = iou
    # Setup the DELF model for extraction.
    self._model = delf_model.Delf(
        block3_strides=block3_strides, name='DELF')

  def LoadWeights(self, checkpoint_path):
    self._model.load_weights(checkpoint_path)

  @tf.function(input_signature=[
      tf.TensorSpec(shape=[None, None, 3], dtype=tf.uint8, name='input_image'),
      tf.TensorSpec(shape=[None], dtype=tf.float32, name='input_scales'),
      tf.TensorSpec(shape=(), dtype=tf.int32, name='input_max_feature_num'),
      tf.TensorSpec(shape=(), dtype=tf.float32, name='input_abs_thres')
  ])
  def ExtractFeatures(self, input_image, input_scales, input_max_feature_num,
                      input_abs_thres):

    extracted_features = export_model_utils.ExtractLocalFeatures(
        input_image, input_scales, input_max_feature_num, input_abs_thres,
        self._iou, lambda x: self._model(x, training=False),
        self._stride_factor)

    named_output_tensors = {}
    named_output_tensors['boxes'] = tf.identity(
        extracted_features[0], name='boxes')
    named_output_tensors['features'] = tf.identity(
        extracted_features[1], name='features')
    named_output_tensors['scales'] = tf.identity(
        extracted_features[2], name='scales')
    named_output_tensors['scores'] = tf.identity(
        extracted_features[3], name='scores')
    return named_output_tensors


def main(argv):
  if len(argv) > 1:
    raise app.UsageError('Too many command-line arguments.')

  export_path = FLAGS.export_path
  if os.path.exists(export_path):
    raise ValueError(f'Export_path {export_path} already exists. Please '
                     'specify a different path or delete the existing one.')

  module = _ExtractModule(FLAGS.block3_strides, FLAGS.iou)

  # Load the weights.
  checkpoint_path = FLAGS.ckpt_path
  module.LoadWeights(checkpoint_path)
  print('Checkpoint loaded from ', checkpoint_path)

  # Save the module
  tf.saved_model.save(module, export_path)


if __name__ == '__main__':
  app.run(main)
