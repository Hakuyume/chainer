# Modified work:
# -----------------------------------------------------------------------------
# Copyright (c) 2018 Preferred Infrastructure, Inc.
# Copyright (c) 2018 Preferred Networks, Inc.
# -----------------------------------------------------------------------------

# Original work:
# -----------------------------------------------------------------------------
# Copyright (c) 2015 by Contributors
# \file roi_pooling.cu
# \brief roi pooling operator
# \author Ross Girshick, Kye-Hyeon Kim, Jian Guo
# \changed to roi_align by Elaine Bao
# \file roi_align.cu
# \roi align operator described in Mask RCNN
# -----------------------------------------------------------------------------

import collections

import numpy
import six

from chainer import cuda
from chainer import function
from chainer.utils import type_check


def _pair(x):
    if isinstance(x, collections.Iterable):
        return x
    return x, x


class ROIAlign2D(function.Function):

    """ROI align over a set of 2d planes."""

    def __init__(self, outh, outw, spatial_scale, sampling_ratio=0):
        for arg in ['outh', 'outw']:
            value = eval(arg)
            if not (isinstance(value, int) and value > 0):
                raise TypeError(
                    '{} must be positive integer: {}, {}'
                    .format(arg, type(value), value)
                )
        if isinstance(spatial_scale, int):
            spatial_scale = float(spatial_scale)
        elif not (isinstance(spatial_scale, float) and spatial_scale > 0):
            raise TypeError(
                'spatial_scale must be a positive float number: {}, {}'
                .format(type(spatial_scale), spatial_scale)
            )
        sampling_ratio = _pair(sampling_ratio)
        if not all(isinstance(s, int) and s >= 0 for s in sampling_ratio):
            raise TypeError(
                'sampling_ratio must be integer >= 0 or a pair of it: {}'
                .format(sampling_ratio)
            )

        self.outh, self.outw = outh, outw
        self.spatial_scale = spatial_scale
        self.sampling_ratio = sampling_ratio

    def check_type_forward(self, in_types):
        type_check.expect(in_types.size() == 2)

        x_type, roi_type = in_types
        type_check.expect(
            x_type.dtype == numpy.float32,
            x_type.ndim == 4,
            roi_type.dtype == numpy.float32,
            roi_type.ndim == 2,
            roi_type.shape[1] == 5,
        )

    def forward_cpu(self, inputs):
        self.retain_inputs((1,))
        self._bottom_data_shape = inputs[0].shape

        bottom_data, bottom_rois = inputs
        channels, height, width = bottom_data.shape[1:]
        n_rois = bottom_rois.shape[0]
        top_data = numpy.empty((n_rois, channels, self.outh,
                                self.outw), dtype=bottom_data.dtype)

        pooled_width, pooled_height = self.outw, self.outh
        spatial_scale = self.spatial_scale

        for i in six.moves.range(top_data.size):
            pw = i % pooled_width
            ph = int(i / pooled_width) % pooled_height
            c = int(i / pooled_width / pooled_height) % channels
            n = int(i / pooled_width / pooled_height / channels)

            roi_batch_ind = int(bottom_rois[n, 0])
            roi_start_w = bottom_rois[n, 1] * spatial_scale
            roi_start_h = bottom_rois[n, 2] * spatial_scale
            roi_end_w = bottom_rois[n, 3] * spatial_scale
            roi_end_h = bottom_rois[n, 4] * spatial_scale

            roi_width = max(roi_end_w - roi_start_w, 1.)
            roi_height = max(roi_end_h - roi_start_h, 1.)
            bin_size_h = roi_height / pooled_height
            bin_size_w = roi_width / pooled_width

            if self.sampling_ratio[0] > 0:
                roi_bin_grid_h = self.sampling_ratio[0]
            else:
                roi_bin_grid_h = numpy.ceil(roi_height / pooled_height)
            if self.sampling_ratio[1] > 0:
                roi_bin_grid_w = self.sampling_ratio[1]
            else:
                roi_bin_grid_w = numpy.ceil(roi_width / pooled_width)

            count = roi_bin_grid_h * roi_bin_grid_w

            output_val = 0.
            iy = 0
            while iy < roi_bin_grid_h:
                y = roi_start_h + ph * bin_size_h + \
                    (iy + .5) * bin_size_h / roi_bin_grid_h
                ix = 0
                while ix < roi_bin_grid_w:
                    x = roi_start_w + pw * bin_size_w + \
                        (ix + .5) * bin_size_w / roi_bin_grid_w

                    # bilinear interpolation {{
                    if y < -1 or y > height or x < -1 or x > width:
                        # empty
                        continue

                    if y <= 0:
                        y = 0
                    if x <= 0:
                        x = 0

                    y_low = int(y)
                    x_low = int(x)

                    if y_low >= height - 1:
                        y_high = y_low = height - 1
                        y = float(y_low)
                    else:
                        y_high = y_low + 1

                    if x_low >= width - 1:
                        x_high = x_low = width - 1
                        x = float(x_low)
                    else:
                        x_high = x_low + 1

                    ly = y - y_low
                    lx = x - x_low
                    hy = 1. - ly
                    hx = 1. - lx

                    v1 = bottom_data[roi_batch_ind, c, y_low, x_low]
                    v2 = bottom_data[roi_batch_ind, c, y_low, x_high]
                    v3 = bottom_data[roi_batch_ind, c, y_high, x_low]
                    v4 = bottom_data[roi_batch_ind, c, y_high, x_high]

                    w1 = hy * hx
                    w2 = hy * lx
                    w3 = ly * hx
                    w4 = ly * lx

                    output_val += w1 * v1 + w2 * v2 + w3 * v3 + w4 * v4

                    # }}

                    ix += 1
                iy += 1

            output_val /= count
            top_data[n, c, ph, pw] = output_val

        return top_data,

    def forward_gpu(self, inputs):
        self.retain_inputs((1,))
        self._bottom_data_shape = inputs[0].shape

        bottom_data, bottom_rois = inputs
        channels, height, width = bottom_data.shape[1:]
        n_rois = bottom_rois.shape[0]
        top_data = cuda.cupy.empty((n_rois, channels, self.outh,
                                    self.outw), dtype=bottom_data.dtype)
        cuda.cupy.ElementwiseKernel(
            '''
            raw T bottom_data, T spatial_scale, int32 channels,
            int32 height, int32 width, int32 pooled_height, int32 pooled_width,
            int32 sampling_ratio_h, int32 sampling_ratio_w,
            raw T bottom_rois
            ''',
            'T top_data',
            '''
            int pw = i % pooled_width;
            int ph = (i / pooled_width) % pooled_height;
            int c = (i / pooled_width / pooled_height) % channels;
            int n = i / pooled_width / pooled_height / channels;

            int roi_batch_ind = bottom_rois[n * 5 + 0];

            T roi_start_w = bottom_rois[n * 5 + 1] * spatial_scale;
            T roi_start_h = bottom_rois[n * 5 + 2] * spatial_scale;
            T roi_end_w = bottom_rois[n * 5 + 3] * spatial_scale;
            T roi_end_h = bottom_rois[n * 5 + 4] * spatial_scale;

            // Force malformed ROIs to be 1x1
            T roi_width = max(roi_end_w - roi_start_w, (T)1.);
            T roi_height = max(roi_end_h - roi_start_h, (T)1.);
            T bin_size_h = static_cast<T>(roi_height)
                            / static_cast<T>(pooled_height);
            T bin_size_w = static_cast<T>(roi_width)
                            / static_cast<T>(pooled_width);

            int bottom_data_offset =
                (roi_batch_ind * channels + c) * height * width;

            // We use roi_bin_grid to sample the grid and mimic integral
            int roi_bin_grid_h = (sampling_ratio_h > 0)
                ? sampling_ratio_h
                : ceil(roi_height / pooled_height);  // e.g. = 2
            int roi_bin_grid_w = (sampling_ratio_w > 0)
                ? sampling_ratio_w
                : ceil(roi_width / pooled_width);

            // We do average (integral) pooling inside a bin
            T count = roi_bin_grid_h * roi_bin_grid_w;  // e.g. = 4

            T output_val = 0.;
            for (int iy = 0; iy < roi_bin_grid_h; iy++)  // e.g. iy = 0, 1
            {
                T y = roi_start_h + ph * bin_size_h +
                    static_cast<T>(iy + .5f) * bin_size_h /
                        static_cast<T>(roi_bin_grid_h);  // e.g. 0.5, 1.5
                for (int ix = 0; ix < roi_bin_grid_w; ix++) {
                    T x = roi_start_w + pw * bin_size_w +
                        static_cast<T>(ix + .5f) * bin_size_w /
                            static_cast<T>(roi_bin_grid_w);

                    // bilinear_interpolation {{

                    // deal with cases that inverse elements are
                    // out of feature map boundary
                    if (y < -1. || y > height || x < -1. || x > width) {
                        // empty
                        continue;
                    }

                    if (y <= 0) {
                        y = 0;
                    }
                    if (x <= 0) {
                        x = 0;
                    }

                    int y_low = (int)y;
                    int x_low = (int)x;
                    int y_high;
                    int x_high;

                    if (y_low >= height - 1) {
                        y_high = y_low = height - 1;
                        y = (T)y_low;
                    } else {
                        y_high = y_low + 1;
                    }

                    if (x_low >= width - 1) {
                        x_high = x_low = width - 1;
                        x = (T)x_low;
                    } else {
                        x_high = x_low + 1;
                    }

                    T ly = y - y_low;
                    T lx = x - x_low;
                    T hy = 1. - ly;
                    T hx = 1. - lx;
                    // do bilinear interpolation
                    T v1 = bottom_data[bottom_data_offset +
                                       y_low * width + x_low];
                    T v2 = bottom_data[bottom_data_offset +
                                       y_low * width + x_high];
                    T v3 = bottom_data[bottom_data_offset +
                                       y_high * width + x_low];
                    T v4 = bottom_data[bottom_data_offset +
                                       y_high * width + x_high];
                    T w1 = hy * hx;
                    T w2 = hy * lx;
                    T w3 = ly * hx;
                    T w4 = ly * lx;

                    // }}

                    output_val += (w1 * v1 + w2 * v2 + w3 * v3 + w4 * v4);
                }
            }
            output_val /= count;

            top_data = output_val;
            ''', 'roi_align_2d_fwd'
        )(bottom_data, self.spatial_scale, channels, height, width,
          self.outh, self.outw, self.sampling_ratio[0], self.sampling_ratio[1],
          bottom_rois, top_data)

        return top_data,

    def backward_cpu(self, inputs, gy):
        bottom_rois = inputs[1]
        channels, height, width = self._bottom_data_shape[1:]
        bottom_diff = numpy.zeros(self._bottom_data_shape, gy[0].dtype)

        spatial_scale = self.spatial_scale
        pooled_height = self.outh
        pooled_width = self.outw
        top_diff = gy[0]

        for i in six.moves.range(top_diff.size):
            pw = i % pooled_width
            ph = int(i / pooled_width) % pooled_height
            c = int(i / pooled_width / pooled_height) % channels
            n = int(i / pooled_width / pooled_height / channels)

            roi_batch_ind = int(bottom_rois[n, 0])
            roi_start_w = bottom_rois[n, 1] * spatial_scale
            roi_start_h = bottom_rois[n, 2] * spatial_scale
            roi_end_w = bottom_rois[n, 3] * spatial_scale
            roi_end_h = bottom_rois[n, 4] * spatial_scale

            roi_width = max(roi_end_w - roi_start_w, 1.)
            roi_height = max(roi_end_h - roi_start_h, 1.)
            bin_size_h = roi_height / pooled_height
            bin_size_w = roi_width / pooled_width

            top_diff_this_bin = top_diff[n, c, ph, pw]

            if self.sampling_ratio[0] > 0:
                roi_bin_grid_h = self.sampling_ratio[0]
            else:
                roi_bin_grid_h = numpy.ceil(roi_height / pooled_height)
            if self.sampling_ratio[1] > 0:
                roi_bin_grid_w = self.sampling_ratio[1]
            else:
                roi_bin_grid_w = numpy.ceil(roi_width / pooled_width)

            count = roi_bin_grid_h * roi_bin_grid_w

            iy = 0
            while iy < roi_bin_grid_h:
                y = roi_start_h + ph * bin_size_h + \
                    (iy + .5) * bin_size_h / roi_bin_grid_h
                ix = 0
                while ix < roi_bin_grid_w:
                    x = roi_start_w + pw * bin_size_w + \
                        (ix + .5) * bin_size_w / roi_bin_grid_w

                    # bilinear_interpolation_gradient {{
                    if y < -1 or y > height or x < -1 or x > width:
                        # empty
                        continue

                    if y <= 0:
                        y = 0
                    if x <= 0:
                        x = 0

                    y_low = int(y)
                    x_low = int(x)

                    if y_low >= height - 1:
                        y_high = y_low = height - 1
                        y = float(y_low)
                    else:
                        y_high = y_low + 1

                    if x_low >= width - 1:
                        x_high = x_low = width - 1
                        x = float(x_low)
                    else:
                        x_high = x_low + 1

                    ly = y - y_low
                    lx = x - x_low
                    hy = 1. - ly
                    hx = 1. - lx

                    w1 = hy * hx
                    w2 = hy * lx
                    w3 = ly * hx
                    w4 = ly * lx
                    # }}

                    g1 = top_diff_this_bin * w1 / count
                    g2 = top_diff_this_bin * w2 / count
                    g3 = top_diff_this_bin * w3 / count
                    g4 = top_diff_this_bin * w4 / count

                    if (x_low >= 0 and x_high >= 0 and
                            y_low >= 0 and y_high >= 0):
                        bottom_diff[roi_batch_ind, c, y_low, x_low] += g1
                        bottom_diff[roi_batch_ind, c, y_low, x_high] += g2
                        bottom_diff[roi_batch_ind, c, y_high, x_low] += g3
                        bottom_diff[roi_batch_ind, c, y_high, x_high] += g4
                    ix += 1
                iy += 1

        return bottom_diff, None

    def backward_gpu(self, inputs, gy):
        bottom_rois = inputs[1]
        channels, height, width = self._bottom_data_shape[1:]
        bottom_diff = cuda.cupy.zeros(self._bottom_data_shape, gy[0].dtype)
        cuda.cupy.ElementwiseKernel(
            '''
            raw T top_diff,
            int32 num_rois, T spatial_scale,
            int32 channels, int32 height, int32 width,
            int32 pooled_height, int32 pooled_width,
            int32 sampling_ratio_h, int32 sampling_ratio_w,
            raw T bottom_rois
            ''',
            'raw T bottom_diff',
            '''
            // (n, c, h, w) coords in bottom data
            int pw = i % pooled_width;
            int ph = (i / pooled_width) % pooled_height;
            int c = (i / pooled_width / pooled_height) % channels;
            int n = i / pooled_width / pooled_height / channels;

            // Do not using rounding; this implementation detail is critical
            int roi_batch_ind = bottom_rois[n * 5 + 0];
            T roi_start_w = bottom_rois[n * 5 + 1] * spatial_scale;
            T roi_start_h = bottom_rois[n * 5 + 2] * spatial_scale;
            T roi_end_w = bottom_rois[n * 5 + 3] * spatial_scale;
            T roi_end_h = bottom_rois[n * 5 + 4] * spatial_scale;

            // Force malformed ROIs to be 1x1
            T roi_width = max(roi_end_w - roi_start_w, (T)1.);
            T roi_height = max(roi_end_h - roi_start_h, (T)1.);
            T bin_size_h = static_cast<T>(roi_height) /
                static_cast<T>(pooled_height);
            T bin_size_w = static_cast<T>(roi_width) /
                static_cast<T>(pooled_width);

            int bottom_diff_offset =
                (roi_batch_ind * channels + c) * height * width;

            int top_offset = (n * channels + c) * pooled_height * pooled_width;
            T top_diff_this_bin =
                top_diff[top_offset + ph * pooled_width + pw];

            // We use roi_bin_grid to sample the grid and mimic integral
            int roi_bin_grid_h = (sampling_ratio_h > 0)
                ? sampling_ratio_h
                : ceil(roi_height / pooled_height); // e.g. = 2
            int roi_bin_grid_w = (sampling_ratio_w > 0)
                ? sampling_ratio_w
                : ceil(roi_width / pooled_width);

            // We do average (integral) pooling inside a bin
            T count = roi_bin_grid_h * roi_bin_grid_w;  // e.g. = 4

            for (int iy = 0; iy < roi_bin_grid_h; iy++) {
                T y = roi_start_h + ph * bin_size_h +
                    static_cast<T>(iy + .5f) * bin_size_h /
                        static_cast<T>(roi_bin_grid_h);  // e.g. 0.5, 1.5
                for (int ix = 0; ix < roi_bin_grid_w; ix++) {
                    T x = roi_start_w + pw * bin_size_w +
                        static_cast<T>(ix + .5f) * bin_size_w /
                            static_cast<T>(roi_bin_grid_w);

                    T w1, w2, w3, w4;
                    int x_low, x_high, y_low, y_high;

                    // bilinear_interpolation_gradient {{

                    // deal with cases that inverse elements are
                    // out of feature map boundary
                    if (y < -1. || y > height || x < -1. || x > width) {
                        // empty
                        continue;
                    }

                    if (y <= 0) {
                        y = 0;
                    }
                    if (x <= 0) {
                        x = 0;
                    }

                    y_low = (int)y;
                    x_low = (int)x;

                    if (y_low >= height - 1) {
                        y_high = y_low = height - 1;
                        y = (T)y_low;
                    } else {
                        y_high = y_low + 1;
                    }

                    if (x_low >= width - 1) {
                        x_high = x_low = width - 1;
                        x = (T)x_low;
                    } else {
                        x_high = x_low + 1;
                    }

                    T ly = y - y_low;
                    T lx = x - x_low;
                    T hy = 1. - ly;
                    T hx = 1. - lx;

                    w1 = hy * hx;
                    w2 = hy * lx;
                    w3 = ly * hx;
                    w4 = ly * lx;

                    // }}

                    T g1 = top_diff_this_bin * w1 / count;
                    T g2 = top_diff_this_bin * w2 / count;
                    T g3 = top_diff_this_bin * w3 / count;
                    T g4 = top_diff_this_bin * w4 / count;

                    if (x_low >= 0 && x_high >= 0 &&
                            y_low >= 0 && y_high >= 0) {
                        atomicAdd(&bottom_diff[bottom_diff_offset +
                                               y_low * width + x_low], g1);
                        atomicAdd(&bottom_diff[bottom_diff_offset +
                                               y_low * width + x_high], g2);
                        atomicAdd(&bottom_diff[bottom_diff_offset +
                                               y_high * width + x_low], g3);
                        atomicAdd(&bottom_diff[bottom_diff_offset +
                                               y_high * width + x_high], g4);
                    }
                }
            }
            ''', 'roi_align_2d_bwd'
        )(gy[0], bottom_rois.shape[0],
          self.spatial_scale, channels, height, width, self.outh, self.outw,
          self.sampling_ratio[0], self.sampling_ratio[1],
          bottom_rois, bottom_diff, size=gy[0].size)

        return bottom_diff, None


def roi_align_2d(x, rois, outh, outw, spatial_scale, sampling_ratio=0):
    """Spatial Region of Interest (ROI) align function.

    This function acts similarly to :class:`~functions.ROIPooling2D`, but
    it computes the maximum of input spatial patch with bilinear interpolation
    for each channel with the region of interest.

    Args:
        x (~chainer.Variable): Input variable. The shape is expected to be
            4 dimentional: (n: batch, c: channel, h, height, w: width).
        rois (~chainer.Variable): Input roi variable. The shape is expected to
            be (n: data size, 5), and each datum is set as below:
            (batch_index, x_min, y_min, x_max, y_max).
        outh (int): Height of output image after pooled.
        outw (int): Width of output image after pooled.
        spatial_scale (float): Scale of the roi is resized.
        sampling_ratio (int or tuple of int): Sampling step for the alignment.
            It must meet >=0 and is automatically decided when 0 is passed.
            Use of different ratio in height and width axis is also supported
            by passing tuple of int as (sampling_ratio_h, sampling_ratio_w).

    Returns:
        ~chainer.Variable: Output variable.

    See the original paper proposing ROIAlign:
    `Mask R-CNN <https://arxiv.org/abs/1703.06870>`_.

    """
    return ROIAlign2D(outh, outw, spatial_scale, sampling_ratio)(x, rois)
