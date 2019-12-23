# --------------------------------------------------------
# Faster R-CNN
# Copyright (c) 2015 Microsoft
# Licensed under The MIT License [see LICENSE for details]
# Written by Ross Girshick
# --------------------------------------------------------
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from light_config import cfg
import numpy as np
import numpy.random as npr
from detection_opr.utils.bbox_transform import bbox_transform
from utils.py_faster_rcnn_utils.cython_bbox import bbox_overlaps

def proposal_target_layer(batch_rpn_rois, batch_gt_boxes, batch_im_info):
    """
    Assign object detection proposals to ground-truth targets. Produces proposal
    classification labels and bounding-box regression targets.
    """
    # Proposal ROIs (0, x1, y1, x2, y2) coming from RPN

    batch_rois = []
    batch_labels = []
    batch_bbox_targets = []

    for b_id in range(cfg.train_batch_per_gpu):
        im_info = batch_im_info[b_id]
        gt_boxes = batch_gt_boxes[b_id][:int(im_info[5])]
        rois_inds = np.where(batch_rpn_rois[:, 0] == b_id)
        all_rois = batch_rpn_rois[rois_inds]

        # Include ground-truth boxes in the set of candidate rois
        if cfg.TRAIN.USE_GT:
            ones = np.ones((gt_boxes.shape[0], 1), dtype=gt_boxes.dtype)
            all_rois = np.vstack(
                (all_rois, np.hstack((ones * b_id, gt_boxes[:, :-1])))
            )
            # not sure if it a wise appending, but anyway i am not using it
            # ones = np.ones((gt_boxes.shape[0]), dtype=gt_boxes.dtype)
            # all_scores = np.hstack((all_scores, ones))

        rois_per_image = np.inf if cfg.TRAIN.BATCH_SIZE == -1 else cfg.TRAIN.BATCH_SIZE
        fg_rois_per_image = np.round(cfg.TRAIN.FG_FRACTION * rois_per_image)

        # Sample rois with classification labels and bounding box regression
        labels, rois, bbox_targets, bbox_inside_weights = _sample_rois(
            all_rois, gt_boxes, fg_rois_per_image,
            rois_per_image, cfg.num_classes)

        rois = rois.reshape(-1, 5)
        labels = labels.reshape(-1, 1)
        bbox_targets = bbox_targets.reshape(-1, cfg.num_classes * 4)

        batch_rois.append(rois)
        batch_labels.append(labels)
        batch_bbox_targets.append(bbox_targets)
    batch_rois = np.vstack(batch_rois)
    batch_labels = np.vstack(batch_labels)
    batch_bbox_targets = np.vstack(batch_bbox_targets)

    return batch_rois, batch_labels, batch_bbox_targets


def _get_bbox_regression_labels(bbox_target_data, num_classes):
    """Bounding-box regression targets (bbox_target_data) are stored in a
    compact form N x (class, tx, ty, tw, th)

    This function expands those targets into the 4-of-4*K representation used
    by the network (i.e. only one class has non-zero targets).

    Returns:
        bbox_target (ndarray): N x 4K blob of regression targets
        bbox_inside_weights (ndarray): N x 4K blob of loss weights
    """

    clss = bbox_target_data[:, 0]
    bbox_targets = np.zeros((clss.size, 4 * num_classes), dtype=np.float32)
    bbox_inside_weights = np.zeros(bbox_targets.shape, dtype=np.float32)
    inds = np.where(clss > 0)[0]
    for ind in inds:
        cls = clss[ind]
        start = int(4 * cls)
        end = start + 4
        bbox_targets[ind, start:end] = bbox_target_data[ind, 1:]
        bbox_inside_weights[ind, start:end] = cfg.TRAIN.BBOX_INSIDE_WEIGHTS
    return bbox_targets, bbox_inside_weights


def _compute_targets(ex_rois, gt_rois, labels):
    """Compute bounding-box regression targets for an image."""

    assert ex_rois.shape[0] == gt_rois.shape[0]
    assert ex_rois.shape[1] == 4
    assert gt_rois.shape[1] == 4

    targets = bbox_transform(ex_rois, gt_rois)
    if cfg.TRAIN.BBOX_NORMALIZE_TARGETS_PRECOMPUTED:
        # Optionally normalize targets by a precomputed mean and stdev
        targets = ((targets - np.array(cfg.TRAIN.BBOX_NORMALIZE_MEANS))
                   / np.array(cfg.TRAIN.BBOX_NORMALIZE_STDS))
    return np.hstack(
        (labels[:, np.newaxis], targets)).astype(np.float32, copy=False)


def _sample_rois(all_rois, gt_boxes, fg_rois_per_image,
                 rois_per_image, num_classes):
    """Generate a random sample of RoIs comprising foreground and background
    examples.
    """
    # overlaps: (rois x gt_boxes)
    overlaps = bbox_overlaps(
        np.ascontiguousarray(all_rois[:, 1:5], dtype=np.float),
        np.ascontiguousarray(gt_boxes[:, :4], dtype=np.float))
    gt_assignment = overlaps.argmax(axis=1)
    max_overlaps = overlaps.max(axis=1)
    labels = gt_boxes[gt_assignment, 4]

    # Select foreground RoIs as those with >= FG_THRESH overlap
    fg_inds = np.where(max_overlaps >= cfg.TRAIN.FG_THRESH)[0]
    # Guard against the case when an image has fewer than fg_rois_per_image
    # Select background RoIs as those within [BG_THRESH_LO, BG_THRESH_HI)
    bg_inds = np.where((max_overlaps < cfg.TRAIN.BG_THRESH_HI) &
                       (max_overlaps >= cfg.TRAIN.BG_THRESH_LO))[0]

    # Small modification to the original version where we ensure a fixed number
    # of regions are sampled

    '''
    if fg_inds.size > 0 and bg_inds.size > 0:
        fg_rois_per_image = min(fg_rois_per_image, fg_inds.size)
        fg_inds = npr.choice(fg_inds, size=int(fg_rois_per_image),
                             replace=False)
        bg_rois_per_image = rois_per_image - fg_rois_per_image
        to_replace = bg_inds.size < bg_rois_per_image
        bg_inds = npr.choice(bg_inds, size=int(bg_rois_per_image),
                             replace=to_replace)
    elif fg_inds.size > 0:
        to_replace = fg_inds.size < rois_per_image
        fg_inds = npr.choice(fg_inds, size=int(rois_per_image),
                             replace=to_replace)
        fg_rois_per_image = rois_per_image
    elif bg_inds.size > 0:
        to_replace = bg_inds.size < rois_per_image
        bg_inds = npr.choice(bg_inds, size=int(rois_per_image),
                             replace=to_replace)
        fg_rois_per_image = 0
    else:
        import pdb
        pdb.set_trace()

    '''
    # Guard against the case when an image has fewer than fg_rois_per_image
    # foreground RoIs
    fg_rois_per_this_image = min(fg_rois_per_image, fg_inds.size)
    # Sample foreground regions without replacement
    if fg_inds.size > 0:
        fg_inds = npr.choice(fg_inds, size=int(fg_rois_per_this_image), replace=False)
    # Compute number of background RoIs to take from this image (guarding
    # against there being fewer than desired)
    bg_rois_per_this_image = rois_per_image - fg_rois_per_this_image
    bg_rois_per_this_image = min(bg_rois_per_this_image, bg_inds.size)
    # Sample background regions without replacement
    if bg_inds.size > 0:
        bg_inds = npr.choice(bg_inds, size=int(bg_rois_per_this_image), replace=False)


    # The indices that we're selecting (both fg and bg)
    keep_inds = np.append(fg_inds, bg_inds)

    # pad more to ensure a fixed minibatch size
    #while keep_inds.shape[0] < rois_per_image:
    #    gap = np.minimum(len(all_rois), rois_per_image - keep_inds.shape[0])
    #    gap_indexes = npr.choice(range(len(all_rois)), size=gap, replace=False)
    #    keep_inds = np.append(keep_inds, gap_indexes)

    # Select sampled values from various arrays:
    labels = labels[keep_inds]
    # Clamp labels for the background RoIs to 0

    #*******labels[int(fg_rois_per_image):] = 0
    labels[int(fg_rois_per_this_image):] = 0
    rois = all_rois[keep_inds]
    #roi_scores = all_scores[keep_inds]

    bbox_target_data = _compute_targets(
        rois[:, 1:5], gt_boxes[gt_assignment[keep_inds], :4], labels)

    bbox_targets, bbox_inside_weights = \
        _get_bbox_regression_labels(bbox_target_data, num_classes)

    #return labels, rois, roi_scores, bbox_targets, bbox_inside_weights
    return labels, rois, bbox_targets, bbox_inside_weights
