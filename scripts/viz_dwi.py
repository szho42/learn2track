import os
import argparse
import numpy as np
import matplotlib.pyplot as plt

from learn2track import neurotools


def build_argparser():

    DESCRIPTION = ("Script to visualize DWIs (histograms, etc).")
    p = argparse.ArgumentParser(description=DESCRIPTION)

    # Dataset options
    p.add_argument('subjects', nargs='+',
                   help='file containing data (as generated by `process_streamlines.py`).')

    return p


def main():
    parser = build_argparser()
    args = parser.parse_args()

    fig, ax = plt.subplots(1)
    colors = ['blue', 'orange', 'magenta', 'pink', 'darkgreen']
    for subject_file, color in zip(args.subjects, colors):
        subject_id = os.path.basename(subject_file)[:-4]
        print("Loading {}...".format(subject_id))
        tracto_data = neurotools.TractographyData.load(subject_file)

        dwi = tracto_data.signal
        bvals = tracto_data.gradients.bvals
        bvecs = tracto_data.gradients.bvecs
        volume = neurotools.resample_dwi(dwi, bvals, bvecs).astype(np.float32)

        idx = volume.sum(axis=-1).nonzero()
        means = volume[idx].mean(axis=0)
        stds = 0.1 * volume[idx].std(axis=0)

        t = np.arange(1, len(means)+1)
        ax.plot(t, means, lw=2, label="mean {}".format(subject_id), color=color)
        ax.fill_between(t, means+stds, means-stds, facecolor=color, alpha=0.5)

    plt.legend()
    plt.show()


if __name__ == '__main__':
    main()
