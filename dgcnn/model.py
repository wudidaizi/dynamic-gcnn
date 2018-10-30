from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
import tensorflow.python.platform
import tensorflow as tf
import tensorflow.contrib.slim as slim
import dgcnn

def build(point_cloud, flags):

  num_edge_conv = int(flags.EDGE_CONV_LAYERS)
  num_edge_filters = flags.EDGE_CONV_FILTERS
  num_fc = int(flags.FC_LAYERS)
  num_fc_filters = flags.FC_FILTERS
  is_training   = bool(flags.TRAIN)
  k = int(flags.KVALUE)
  debug = bool(flags.DEBUG)
  num_class = int(flags.NUM_CLASS)
  
  net = point_cloud
  batch_size = tf.shape(net)[0]
  num_point = tf.shape(net)[1]
  if debug:
    print('\n')
    print('Shape {:s} ... Name {:s}'.format(net.shape,net.name))

  if flags.MODEL_NAME == 'dgcnn':
    tensors = dgcnn.ops.repeat_edge_conv(net,
                                         repeat=num_edge_conv,
                                         k=k,
                                         num_filters=num_edge_filters,
                                         trainable=is_training,
                                         debug=debug)
  elif flags.MODEL_NAME in ['residual-dgcnn','residual-dgcnn-nofc']:
    tensors = dgcnn.ops.repeat_residual_edge_conv(net,
                                                  repeat=num_edge_conv,
                                                  k=k,
                                                  num_filters=num_edge_filters,
                                                  trainable=is_training,
                                                  debug=debug)
  else:
    print('Unsupported MODEL_NAME: %s' % flags.MODEL_NAME)
    raise NotImplementedError

  if flags.MODEL_NAME == 'residual-dgcnn-nofc':
    net = slim.conv2d(inputs      = tensors[-1],
                      num_outputs = num_class,
                      kernel_size = 1,
                      stride      = 1,
                      trainable   = True,
                      padding     = 'VALID',
                      normalizer_fn = slim.batch_norm,
                      scope       = 'Final')
    if debug: print('Shape {:s} ... Name {:s}'.format(net.shape,net.name))
    
    net = tf.squeeze(net, axis=-2)
    if debug: print('Shape {:s} ... Name {:s}'.format(net.shape,net.name))
    return net
    
  concat = []
  for i in range(num_edge_conv):
    concat.append(tensors[3*i+2])
  concat = tf.concat(concat,axis=-1)

  net = slim.conv2d(inputs      = concat,
                    num_outputs = 1024,
                    kernel_size = 1,
                    stride      = 1,
                    trainable   = True,
                    padding     = 'VALID',
                    normalizer_fn = slim.batch_norm,
                    scope       = 'MergedEdgeConv')
  if debug: print('Shape {:s} ... Name {:s}'.format(net.shape,net.name))
  tensors.append(net)

  from tensorflow.python.ops import gen_nn_ops
  net = gen_nn_ops.max_pool_v2(net, ksize=[1,num_point,1,1], strides=[1,1,1,1], padding='VALID', name='maxpool0')
  if debug: print('Shape {:s} ... Name {:s}'.format(net.shape,net.name))

  net = tf.reshape(net,[batch_size,-1,1,1024])
  net  = tf.tile(net, [1, num_point, 1, 1])
  if debug: print('Shape {:s} ... Name {:s}'.format(net.shape,net.name))
  concat = [net] + tensors

  net = tf.concat(values=concat, axis=3)
  if debug: print('Shape {:s} ... Name {:s}'.format(net.shape,net.name))

  net = dgcnn.ops.fc(net=net, repeat=num_fc, num_filters=num_fc_filters, trainable=is_training, debug=debug)

  if is_training:
    net = tf.nn.dropout(net, 0.7, None)
    if debug: print('Shape {:s} ... Name {:s}'.format(net.shape,net.name))
  net = tf.squeeze(net,axis=-2)
  if debug: print('Shape {:s} ... Name {:s}'.format(net.shape,net.name))

  # Clustering
  dist = dgcnn.ops.dist_nn(net)
  if debug: print('Shape {:s} ... Name {:s}'.format(dist.shape,dist.name))

  # Confidence
  conf = net
  with tf.variable_scope('ScoreEdgeConv'):
    num_conf_filters = num_fc_filters
    if not type(num_conf_filters) == type(int()):
      num_conf_filters = num_conf_filters[-1]
    conf = dgcnn.ops.edge_conv(point_cloud=conf,
                               k=k,
                               num_filters=num_conf_filters,
                               trainable=is_training,
                               debug=debug)
    conf = slim.conv2d(inputs      = conf[-1],
                       num_outputs = 1,
                       kernel_size = 1,
                       stride      = 1,
                       trainable   = True,
                       padding     = 'VALID',
                       normalizer_fn = slim.batch_norm,
                       scope       = 'ScoreFinal')
    conf = tf.squeeze(conf,axis=[2,3])
  if debug: print('Shape {:s} ... Name {:s}'.format(conf.shape,conf.name))
  
  return dist,conf

