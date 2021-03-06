# %load pose_demo.py
#!/usr/bin/env python
"""
Pose predictions in Python.

Caffe must be available on the Pythonpath for this to work. The methods can
be imported and used directly, or the command line interface can be used. In
the latter case, adjust the log-level to your needs. The maximum image size
for one prediction can be adjusted with the variable _MAX_SIZE so that it
still fits in GPU memory, all larger images are split in sufficiently small
parts.

Authors: Christoph Lassner, based on the MATLAB implementation by Eldar
  Insafutdinov.
"""
# pylint: disable=invalid-name
import os as _os
import logging as _logging
import glob as _glob
import numpy as _np
import scipy as _scipy
import click as _click
import caffe as _caffe
import h5py

from estimate_pose import estimate_pose

_LOGGER = _logging.getLogger(__name__)


def _npcircle(image, cx, cy, radius, color, transparency=0.0):
    """Draw a circle on an image using only numpy methods."""
    radius = int(radius)
    cx = int(cx)
    cy = int(cy)
    y, x = _np.ogrid[-radius: radius, -radius: radius]
    index = x**2 + y**2 <= radius**2
    image[cy-radius:cy+radius, cx-radius:cx+radius][index] = (
        image[cy-radius:cy+radius, cx-radius:cx+radius][index].astype('float32') * transparency +
        _np.array(color).astype('float32') * (1.0 - transparency)).astype('uint8')


###############################################################################
# Command line interface.
###############################################################################

@_click.command()
@_click.argument('image_name',
                 type=_click.Path(exists=True, dir_okay=True, readable=True))
@_click.option('--out_name',
               type=_click.Path(dir_okay=True, writable=True),
               help='The result location to use. By default, use `image_name`_pose.npz.',
               default=None)
@_click.option('--scales',
               type=_click.STRING,
               help=('The scales to use, comma-separated. The most confident '
                     'will be stored. Default: 1.'),
               default='1.')
@_click.option('--visualize',
               type=_click.BOOL,
               help='Whether to create a visualization of the pose. Default: True.',
               default=True)
@_click.option('--folder_image_suffix',
               type=_click.STRING,
               help=('The ending to use for the images to read, if a folder is '
                     'specified. Default: .png.'),
               default='.png')
@_click.option('--use_cpu',
               type=_click.BOOL,
               is_flag=True,
               help='Use CPU instead of GPU for predictions.',
               default=False)
@_click.option('--gpu',
               type=_click.INT,
               help='GPU device id.',
               default=0)

# python ./pose_demo.py /data/aron0/ --folder_image_suffix .jpg --gpu 1 --visualize False
def predict_pose_from(image_name,
                      out_name=None,
                      scales='1.',
                      visualize=True,
                      folder_image_suffix='.png',
                      use_cpu=False,
                      gpu=0):
    """
    Load an image file, predict the pose and write it out.
    
    `IMAGE_NAME` may be an image or a directory, for which all images with
    `folder_image_suffix` will be processed.
    """
    model_def = '../../models/deepercut/ResNet-152.prototxt'
    model_bin = '../../models/deepercut/ResNet-152.caffemodel'
    scales = [float(val) for val in scales.split(',')]
    if _os.path.isdir(image_name):
        folder_name = image_name[:]
        _LOGGER.info("Specified image name is a folder. Processing all images "
                     "with suffix %s.", folder_image_suffix)
        images = _glob.glob(_os.path.join(folder_name, '*' + folder_image_suffix))
        process_folder = True
    else:
        images = [image_name]
        process_folder = False
    if use_cpu:
        _caffe.set_mode_cpu()
    else:
        _caffe.set_mode_gpu()
        _caffe.set_device(gpu)
    out_name_provided = out_name
    if process_folder and out_name is not None and not _os.path.exists(out_name):
        _os.mkdir(out_name)
    for image_name in images:
        extension = _os.path.splitext(image_name)[1] # added by Aron
        folder = _os.path.dirname(image_name) # added by Aron
        
        if out_name_provided is None:
            out_name = image_name + '_pose.npz'
        elif process_folder:
            out_name = _os.path.join(out_name_provided,
                                     _os.path.basename(image_name) + '_pose.npz')
        _LOGGER.info("Predicting the pose on `%s` (saving to `%s`) in best of "
                     "scales %s.", image_name, out_name, scales)
        image = _scipy.misc.imread(image_name)
        if image.ndim == 2:
            _LOGGER.warn("The image is grayscale! This may deteriorate performance!")
            image = _np.dstack((image, image, image))
        else:
            image = image[:, :, ::-1]    
        pose, unary_maps = estimate_pose(image, model_def, model_bin, scales)
        _np.savez_compressed(out_name, pose=pose)
         
        # save heatmaps to h5
        fname = _os.path.join(folder, _os.path.splitext(image_name)[0] + '.h5')
        f = h5py.File(fname, 'w')
        
        # unary_maps order:
        # 0 - R ankle, 1 - r knee, 2 - r hip, 3 - l hip, 4 - l knee, 5 - l ankle, 
        # 6 - pelvis, 7 - thorax, # MISSING!
        # 8 - upper neck, 9 - head top, 10 - r wrist, 11 - r elbow, 12 - r shoulder, 13 - l shoulder, 14 - l elbow, 15 - l wrist
        # monocap expected output order:
        # 'RAnk','RKne','RHip','LHip','LKne','LAnk', 'Pelv','Thrx','Neck','Head','RWri','RElb','RSho','LSho','LElb','LWri'
        
        
        # hack to 
        # print('unary_maps.shape: ', unary_maps.shape[0], unary_maps.shape[1], unary_maps.shape[2])
        pelvis = (unary_maps[:,:,2] + unary_maps[:,:,3])/2.
        thorax = (2. * pelvis + unary_maps[:,:,12] + unary_maps[:,:,13])/4.
        um2 = _np.zeros(shape=(unary_maps.shape[0], unary_maps.shape[1], 16), dtype='float32')
        # print('um2.shape: ', um2.shape)
        for j in range(0, 6):
            # print(j, '<-', j)
            um2[:,:,j] = unary_maps[:,:,j]
        um2[:, :, 6] = pelvis
        print(_np.sum(um2[:,:,6]), _np.sum(pelvis))
        # print(6, '<-', 'pelvis')
        um2[:, :, 7] = thorax
        print(_np.sum(um2[:,:,7]), _np.sum(thorax))

        # print(7, '<-', 'thorax')
        for j in range(8, 16):
            # print(j, '<-', j-2)
            um2[:,:,j] = unary_maps[:,:,j-2]
            

        um2 = _np.swapaxes(um2, 0, 2)
        image = _np.swapaxes(image, 0, 2)
        #h5Hm = f.create_dataset('heatmap', um2.shape, dtype='float32')
        f['heatmap'] = um2
        f['image'] = image
        #h5Hm = um2
        #h5Image = f.create_dataset('image', image.shape, dtype='uint8')
        #h5Image = image
        f.close()
        
        if visualize:
            visim = image[:, :, ::-1].copy()
            colors = [[255, 0, 0],[0, 255, 0],[0, 0, 255],[0,245,255],[255,131,250],[255,255,0],
                      [255, 0, 0],[0, 255, 0],[0, 0, 255],[0,245,255],[255,131,250],[255,255,0],
                      [0,0,0],[255,255,255]]
            for p_idx in range(14):
                _npcircle(visim,
                          pose[0, p_idx],
                          pose[1, p_idx],
                          8,
                          colors[p_idx],
                          0.0)
            vis_name = out_name + '_vis.png'
            _scipy.misc.imsave(vis_name, visim)

if __name__ == '__main__':
    _logging.basicConfig(level=_logging.INFO)
    # pylint: disable=no-value-for-parameter
    predict_pose_from()