# -*- coding: utf-8 -*-
##########################################################################
# NSAp - Copyright (C) CEA, 2020
# Distributed under the terms of the CeCILL-B license, as published by
# the CEA-CNRS-INRIA. Refer to the LICENSE file or to
# http://www.cecill.info/licences/Licence_CeCILL-B_V1-en.html
# for details.
##########################################################################

"""
Common functions to transform image.
Code: https://github.com/fepegar/torchio
"""

# Import
import numpy as np
from scipy.spatial.transform import Rotation
from scipy.ndimage import map_coordinates, rotate
from .transform import compose
from .transform import gaussian_random_field
from .transform import affine_flow
from .utils import interval


def affine(arr, rotation=10, translation=10, zoom=0.2, order=3, dist="uniform"):
    """ Random affine transformation.

    The affine translation & rotation parameters are drawn from a lognormal
    distribution - small movements are assumed to occur more often and large
    movements less frequently - or from a uniform distribution.

    Parameters
    ----------
    arr: array
        the input data.
    rotation: float or 2-uplet, default 10
        the rotation in degrees of the simulated movements. Larger
        values generate more distorted images.
    translation: float or 2-uplet, default 10
        the translation in voxel of the simulated movements. Larger
        values generate more distorted images.
    zoom: float, default 0.2
        the zooming magnitude. Larger values generate more distorted images.
    order: int, default 3
        the order of the spline interpolation in the range [0, 5].
    dist: str, default 'uniform'
        the sampling distribution: 'uniform' or 'lognormal'.
    Returns
    -------
    transformed: array
        the transformed input data.
    """
    rotation = interval(rotation)
    translation = interval(translation)
    random_rotations = random_generator(
        rotation, arr.ndim, dist=dist)
    random_translations = random_generator(
        translation, arr.ndim, dist=dist)
    random_zooms = random_generator(
        translation, arr.ndim, dist=dist)
    random_zooms = np.random.uniform(
        low=(1 - zoom), high=(1 + zoom), size=arr.ndim)
    random_rotations = Rotation.from_euler(
        "xyz", random_rotations, degrees=True)
    random_rotations = random_rotations.as_dcm()
    affine = compose(random_translations, random_rotations, random_zooms)
    shape = arr.shape
    flow = affine_flow(affine, shape)
    locs = flow.reshape(len(shape), -1)
    transformed = map_coordinates(arr, locs, order=order, cval=0)
    return transformed.reshape(shape)


def rotation(arr, angles=5, axes=((0, 1), (0, 2), (1, 2)), order=0, dist="uniform"):
    angles = interval(angles)
    random_rotations = random_generator(angles, arr.ndim, dist=dist)
    rot_arr = np.copy(arr)
    for i, ax in enumerate(axes):
        rot_arr = rotate(rot_arr, axes=ax, angle=random_rotations[i], order=order,
                         reshape=False, mode="constant", cval=0)
    return rot_arr


def cutout(arr, patch_size, value=0, random_size=False, inplace=False, localization=None, min_size=None):
    """Apply a cutout on the images
    cf. Improved Regularization of Convolutional Neural Networks with Cutout, arXiv, 2017
    We assume that the square to be cut is inside the image.
    """
    img_shape = np.array(arr.shape)
    if isinstance(patch_size, int):
        size = [patch_size for _ in range(len(img_shape))]
    else:
        size = np.copy(patch_size)
    assert len(size) == len(img_shape), "Incorrect patch dimension."
    indexes = []
    for ndim in range(len(img_shape)):
        if size[ndim] > img_shape[ndim] or size[ndim] < 0:
            size[ndim] = img_shape[ndim]
        if random_size:
            if min_size is None:
                min_size = [0 for _ in range(len(img_shape))]
            size[ndim] = np.random.randint(min_size[ndim], size[ndim])
        if localization is not None:
            delta_before = max(localization[ndim] - size[ndim]//2, 0)
        else:
            delta_before = np.random.randint(0, img_shape[ndim] - size[ndim] + 1)
        indexes.append(slice(delta_before, delta_before + size[ndim]))
    if inplace:
        arr[tuple(indexes)] = value
        return arr
    else:
        arr_cut = np.copy(arr)
        arr_cut[tuple(indexes)] = value
        return arr_cut


def cutout_with_threshold(arr, patch_size, threshold=None, **kwargs):
    if threshold is not None:
        nb_nonzero_voxels = np.count_nonzero(arr)
        nb_of_attempt = 10
        for i in range(nb_of_attempt):
            arr_cut = cutout(arr, patch_size)
            rate_of_removed_voxels = 1 - np.count_nonzero(arr_cut) / nb_nonzero_voxels
            if rate_of_removed_voxels > threshold:
                break
            if i == nb_of_attempt-1:
                raise ValueError(f"Cutout : the patch size {patch_size} is too small for the threshold {threshold}")
        return arr_cut
    else:
        return cutout(arr, patch_size, **kwargs)


def random_cutout(arr, patch_size_ratio, min_size_ratio=None, on_data=False, max_dist=None):
    # FIXME : remove condition of localization when on_data=True ?
    img_shape = np.array(arr.shape)
    patch_size = np.ceil(img_shape * patch_size_ratio).astype(int)
    if min_size_ratio is None:
        min_patch_size = np.zeros(len(img_shape))
    else:
        min_patch_size = np.ceil(img_shape * min_size_ratio).astype(int)
    if on_data:
        nonzero_voxels = np.nonzero(arr)
        index = np.random.randint(0, len(nonzero_voxels[0]))
        localization = np.array([nonzero_voxels[i][index] for i in range(len(nonzero_voxels))])
        while np.any(localization > (img_shape - patch_size//2)) or np.any(localization < patch_size//2):
            index = np.random.randint(0, len(nonzero_voxels[0]))
            localization = [nonzero_voxels[i][index] for i in range(len(nonzero_voxels))]
        arr_cut = cutout(arr, patch_size, localization=localization, random_size=True, min_size=min_patch_size)
    elif max_dist is not None:
        center = img_shape // 2
        localization = [np.random.randint(center[d] - max_dist[d], center[d] + max_dist[d]) for d in img_shape]
        arr_cut = cutout(arr, patch_size, random_size=True, min_size=min_patch_size, localization=localization)
    else:
        arr_cut = cutout(arr, patch_size, random_size=True, min_size=min_patch_size)
    return arr_cut


def flip(arr, axis=None):
    """ Apply a random mirror flip.

    Parameters
    ----------
    arr: array
        the input data.
    axis: int, default None
        apply flip on the specified axis. If not specified, randomize the
        flip axis.

    Returns
    -------
    transformed: array
        the transformed input data.
    """
    if axis is None:
        axis = np.random.randint(low=0, high=arr.ndim, size=1)[0]
    return np.flip(arr, axis=axis)


def deformation(arr, max_displacement=4, alpha=3, order=3):
    """ Apply dense random elastic deformation.

    Reference: Khanal B, Ayache N, Pennec X., Simulating Longitudinal
    Brain MRIs with Known Volume Changes and Realistic Variations in Image
    Intensity, Front Neurosci, 2017.

    Parameters
    ----------
    arr: array
        the input data.
    max_displacement: float, default 4
        the maximum displacement in voxel along each dimension. Larger
        values generate more distorted images.
    alpha: float, default 3
        the power of the power-law momentum distribution. Larger values
        genrate smoother fields.
    order: int, default 3
        the order of the spline interpolation in the range [0, 5].

    Returns
    -------
    transformed: array
        the transformed input data.
    """
    flow_x = gaussian_random_field(
        arr.shape[:2], alpha=alpha, normalize=True)
    flow_x /= flow_x.max()
    flow_x = np.asarray([flow_x] * arr.shape[-1]).transpose(1, 2, 0)

    flow_y = gaussian_random_field(
        arr.shape[:2], alpha=alpha, normalize=True)
    flow_y /= flow_y.max()
    flow_y = np.asarray([flow_y] * arr.shape[-1]).transpose(1, 2, 0)

    flow_z = gaussian_random_field(
        arr.shape[:2], alpha=alpha, normalize=True)
    flow_z /= flow_z.max()
    flow_z = np.asarray([flow_z] * arr.shape[-1]).transpose(1, 2, 0)
    flow = np.asarray([flow_x, flow_y, flow_z])
    flow *= max_displacement
    ranges = [np.arange(size) for size in arr.shape]
    locs = np.asarray(np.meshgrid(*ranges)).transpose(0, 2, 1, 3).astype(float)
    locs += flow
    locs = locs.reshape(len(locs), -1)
    transformed = map_coordinates(arr, locs, order=order, cval=0)
    return transformed.reshape(arr.shape)


def random_generator(interval, size, dist="uniform"):
    """ Random varaible generator.

    Parameters
    ----------
    interval: 2-uplet
        the possible values of the generated random variable.
    size: uplet
        the number of random variables to be drawn from the sampling
        distribution.
    dist: str, default 'uniform'
        the sampling distribution: 'uniform' or 'lognormal'.

    Returns
    -------
    random_variables: array
        the generated random variable.
    """
    np.random.seed()
    if dist == "uniform":
        random_variables = np.random.uniform(
            low=interval[0], high=interval[1], size=size)
    # max height occurs at x = exp(mean - sigma**2)
    # FWHM is found by finding the values of x at 1/2 the max height =
    # exp((mean - sigma**2) + sqrt(2*sigma**2*ln(2))) - exp((mean - sigma**2)
    # - sqrt(2*sigma**2*ln(2)))
    elif dist == "lognormal":
        sign = np.random.randint(0, 2, size=size) * 2 - 1
        sign = sign.astype(np.float)

        random_variables = np.random.lognormal(mean=0., sigma=1., size=size)
        random_variables /= 12.5
        random_variables *= (sign * interval[1])
    else:
        raise ValueError("Unsupported sampling distribution.")
    return random_variables
