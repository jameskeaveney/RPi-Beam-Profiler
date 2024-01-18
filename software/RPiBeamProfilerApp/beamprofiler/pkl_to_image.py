""" Read-in a .pkl image file and plot the image in matplotlib. Save the resulting image as a png and pdf file."""

import glob
import pickle
import sys
import time

import matplotlib.pyplot as plt
import numpy as np

# update matplotlib fonts etc
plt.rc("font", **{"family": "Serif", "serif": ["Times New Roman"]})
params = {
    "axes.labelsize": 13,
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
    "legend.fontsize": 11,
    "mathtext.fontset": "cm",
    "mathtext.rm": "serif",
}
plt.rcParams.update(params)

# Colours
d_purple = [126.0 / 255.0, 49.0 / 255.0, 123.0 / 255.0]  # 	Palatinate Purple	255C
d_black = [35.0 / 255, 31.0 / 255, 32.0 / 255]  # 	Black				BlackC

try:
    cmap = plt.cm.inferno  # type: ignore
except:
    cmap = plt.cm.CMRmap  # type: ignore


def main(filename):
    # read-in data from pkl file
    imgdata = pickle.load(open(filename, "rb"))

    X = np.arange(len(imgdata[0, :]))
    Y = np.arange(len(imgdata[:, 0]))

    # x and y axis integrated slices
    imgX = imgdata.sum(axis=0, dtype=float)
    imgY = imgdata.sum(axis=1, dtype=float)

    # Set up figure
    fig = plt.figure()
    axmain = plt.subplot2grid((6, 6), (0, 0), colspan=5, rowspan=5)
    axH = plt.subplot2grid((6, 6), (5, 0), colspan=5, rowspan=1, sharex=axmain)
    axV = plt.subplot2grid((6, 6), (0, 5), colspan=1, rowspan=5, sharey=axmain)

    axmain.imshow(imgdata, aspect="auto", extent=[0, len(imgX), len(imgY), 0], cmap=cmap)
    axH.plot(X, imgX / imgX.max(), "o", mec=d_purple, ms=5, mfc=None)
    axV.plot(imgY / imgY.max(), Y, "o", mec=d_purple, ms=5, mfc=None)

    # Format figure
    axH.set_xlabel("X position (px)")
    axV.set_ylabel("Y position (px)")
    axV.yaxis.set_label_position("right")
    plt.setp(axmain.get_xticklabels(), visible=False)
    plt.setp(axV.get_yticklabels(), visible=False)
    axmain.tick_params(direction="in", color="w", bottom=1, top=1, left=1, right=1)
    axH.tick_params(direction="in", bottom=1, top=1, left=1, right=1, color=2 * np.array(d_black))
    axV.tick_params(direction="in", bottom=1, top=1, left=1, right=1, color=2 * np.array(d_black))

    # Fill the figure canvas with the plot panels
    plt.tight_layout()

    # Save
    plt.savefig(filename[:-4] + ".png", dpi=300)
    plt.savefig(filename[:-4] + ".pdf")


if __name__ == "__main__":
    main(sys.argv[1])
