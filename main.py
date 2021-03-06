#!/usr/bin/env python

# authors: M. Hieronymus (mhierony@students.uni-mainz.de)
# date:    November 2016
# Debug purpose: cuda-memcheck python main.py --GPU_global --CPU --outdir plots -b 4 -d 16
# python main.py --GPU_global --CPU --outdir plots -b 10 -d 5000 --use_given_edges
from argparse import (ArgumentParser, ArgumentDefaultsHelpFormatter,
                      RawTextHelpFormatter)
from collections import OrderedDict
from copy import deepcopy
from itertools import product
import os
from psutil import virtual_memory
import random as rnd
import sys
from timeit import default_timer as timer
import warnings

import matplotlib
matplotlib.use('agg')
import matplotlib.gridspec as gridspec
import matplotlib.lines as mlines
import matplotlib.patches as mpatches
from matplotlib.patches import Rectangle
import matplotlib.pyplot as plt
from matplotlib.ticker import FormatStrFormatter
import numpy as np
import pandas as pd
import pycuda.autoinit
import pycuda.driver as cuda

import gpu_hist


FTYPE = np.float64


# TODO: record when call to shared memory falls back to global memory


def mkdir(d, mode=0750, warn=True):
    """Simple wrapper around os.makedirs to create a directory but not raise an
    exception if the dir already exists

    Parameters
    ----------
    d : string
        Directory path
    mode : integer
        Permissions on created directory; see os.makedirs for details.
    warn : bool
        Whether to warn if directory already exists.

    """
    try:
        os.makedirs(d, mode=mode)
    except OSError as err:
        if err[0] == 17:
            if warn:
                print('Directory "%s" already exists' %d)
        else:
            raise err
    else:
        print('Created directory "%s"' %d)


def create_array(n_elements, n_dims, device_array, seed=0, ftype=FTYPE):
    """Create an array with values between -360 and 360 (could be any other
    range too)"""
    assert n_elements > 0
    assert n_dims > 0
    rand = np.random.RandomState(seed)
    values = rand.normal(size=(n_elements, n_dims)).astype(ftype)
    if device_array:
        d_values = cuda.mem_alloc(values.nbytes)
        cuda.memcpy_htod(d_values, values)
        return values, d_values
    else:
        return values, values


def create_weights(n_elements, n_dims, seed=0, ftype=FTYPE):
    rand = np.random.RandomState(seed)
    return rand.uniform(size=(n_dims, n_elements)).astype(ftype)


def create_edges(n_bins, n_dims, random=False, seed=0, ftype=FTYPE):
    """Create edges given the number of bins for each dimension"""
    if random:
        rand = np.random.RandomState(seed)
        edges = [(4*np.sort(rand.uniform(n_bins+1))-2).astype(ftype)
                 for d in xrange(n_dims)]
    else:
        edges = [np.linspace(-2, 2, n_bins+1, dtype=ftype)]*n_dims
    return np.asarray(edges, dtype=ftype)


def record_timing(method, info, timings):
    new_info = deepcopy(info)
    new_info['method'] = method
    new_info['n_trials'] = len(timings)
    new_info['time_median'] = np.median(timings)
    new_info['time_mean'] = np.mean(timings)
    new_info['time_min'] = np.min(timings)
    new_info['time_max'] = np.max(timings)
    new_info['time_std'] = np.std(timings)
    return new_info


# Currently only 1D and 2D
def plot_histogram(histogram, edges, outdir, name, no_of_bins):
    """Plots the histogram into specified directory. If the path does not exist
    then it will be created.

    Parameters
    ----------
    histogram : array
    edges : array
    outdir : path
    name : string
    no_of_bins : int (length of edges if edges is given)
    """

    path = [outdir]
    mkdir(os.path.join(*path), warn=False)
    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.grid(b=True, which='major')
    ax.grid(b=True, which='minor', linestyle=':')
    # print "\nHistogram:", name
    # print np.sum(histogram)
    # print histogram
    # print "With edges:"
    # print edges
    # print np.shape(edges)
    # print np.shape(histogram)
    # print len(np.shape(histogram))
    if(len(np.shape(histogram)) == 1):
        width = 60
        if edges is None:
            edges = np.arange(-360, 360, (720/no_of_bins))
            rects = ax.bar(edges, histogram, width)
            ax.set_xticks(edges)
            xtickNames = ax.set_xticklabels(edges)
        else:
            rects = ax.bar(edges[0][0:no_of_bins], histogram, width)
            ax.set_xticks(edges[0])
            xtickNames = ax.set_xticklabels(edges[0])
        ax.xaxis.set_major_formatter(FormatStrFormatter('%.2f'))
        for tick in ax.xaxis.get_major_ticks():
            tick.label.set_fontsize(9)
        for tick in ax.yaxis.get_major_ticks():
            tick.label.set_fontsize(9)
        fig.savefig(outdir+"/"+name)
    elif(len(np.shape(histogram)) == 2):
        X, Y = np.meshgrid(edges[0], edges[1])
        plt.pcolormesh(X, Y, histogram, cmap='rainbow')
        cbar = plt.colorbar(orientation='vertical')
        cbar.ax.tick_params(labelsize=9)
        ax.set_xticks(edges[0])
        ax.set_yticks(edges[1])
        ax.xaxis.set_major_formatter(FormatStrFormatter('%.2f'))
        ax.yaxis.set_major_formatter(FormatStrFormatter('%.2f'))
        for tick in ax.xaxis.get_major_ticks():
            tick.label.set_fontsize(9)
        for tick in ax.yaxis.get_major_ticks():
            tick.label.set_fontsize(9)
        # set the limits of the image
        plt.axis([X[0][0], X[0][len(X[0])-1], Y[0][0], Y[len(Y)-1][len(Y[len(Y)-1])-1]])
        fig.savefig(outdir+"/"+name)
    elif(len(np.shape(histogram)) == 3):
        fig = plt.figure()
        for i in range(0, np.shape(histogram)[0]):
            subplot = len(edges[0])/2*100 + 20 + i + 1
            ax = fig.add_subplot(subplot)
            ax.grid(b=True, which='major')
            ax.grid(b=True, which='minor', linestyle=':')
            X, Y = np.meshgrid(edges[0], edges[1])
            plt.pcolormesh(X, Y, histogram[i], cmap='rainbow')
            cbar = plt.colorbar(orientation='vertical')
            cbar.ax.tick_params(labelsize=9)
            ax.set_xticks(edges[0])
            ax.set_yticks(edges[1])
            ax.xaxis.set_major_formatter(FormatStrFormatter('%.2f'))
            ax.yaxis.set_major_formatter(FormatStrFormatter('%.2f'))
            for tick in ax.xaxis.get_major_ticks():
                tick.label.set_fontsize(9)
            for tick in ax.yaxis.get_major_ticks():
                tick.label.set_fontsize(9)
            # set the limits of the image
            plt.axis([X[0][0], X[0][len(X[0])-1], Y[0][0], Y[len(Y)-1][len(Y[len(Y)-1])-1]])
        fig.savefig(outdir+"/"+name)

    else:
        print "Plots are only availale for 3 or less dimensions. Aborting"


def plot_timings(timings, iterations, amount_of_elements, amount_of_bins,
        outdir, name, used_device_data, max_elements_idx):
    """Print the timings from --test.
    timings have following order:
    timings [dimensions] 1 to 4
            [n_elements] 10e3 to 10e6
            [bins] 5, 50 and 500
            [precision] single_precision, double_precision
            [Code] CPU, GPU_global, GPU_shared
    """
    path = [outdir]
    mkdir(os.path.join(*path), warn=False)
    width = 1.0

    # We start with single precision and subject to number of elements
    # plots x-axis: n_elements, y_axis1: timings, y_axis2: speedup
    for start in range(0, 2):
        fig = plt.figure()
        start = start*2
        gs = gridspec.GridSpec(4, 2, width_ratios=[1,1],
                height_ratios=[0.5, 40, 40, 0.1])
        if used_device_data:
            plot_title = ('Histogram: Speedup and runtime with CPU and GPU\n'
                    'using already allocated device arrays')
        else:
            plot_title = 'Histogram: Speedup and runtime with CPU and GPU'
        plt.suptitle(plot_title, fontsize=16)
        for b in range(start, start+2):
            # print "b: ", b
            # print 2*(b-start)+2
            ax1 = plt.subplot(gs[2*(b-start)+2])
            # Get all the data
            seq_time1 = []
            running_time1_global = []
            running_time1_shared = []
            n_elements1 = []
            for d in range(0, len(timings)):
                for n in range(0, len(timings[d])):
                    n_elements1.append((d+1)*amount_of_elements[n])
                    seq_time1.append(timings[d][n][b][0][0])
                    running_time1_global.append(timings[d][n][b][0][1])
                    running_time1_shared.append(timings[d][n][b][0][2])
            create_subfig(seq_time1, running_time1_global, running_time1_shared,
                    np.asarray(n_elements1), ax1, width,
                    'Number of elements',
                    '(SP)', True, amount_of_bins[b])
            # Next double precision
            # plots x-axis: n_elements, y_axis1: timings, y_axis2: speedup
            ax3 = plt.subplot(gs[2*(b-start)+3])
            seq_time3 = []
            running_time3_global = []
            running_time3_shared = []
            n_elements3 = []
            for d in range(0, len(timings)):
                for n in range(0, len(timings[d])):
                    n_elements3.append((d+1)*amount_of_elements[n])
                    seq_time3.append(timings[d][n][b][0][0])
                    running_time3_global.append(timings[d][n][b][0][1])
                    running_time3_shared.append(timings[d][n][b][0][2])
            create_subfig(seq_time3, running_time3_global, running_time3_shared,
                    np.asarray(n_elements3), ax3, width,
                    'Number of elements',
                    '(DP)', True, amount_of_bins[b])
        # plt.tight_layout()
        with warnings.catch_warnings():
            # This raises warnings since tight layout cannot
            # handle gridspec automatically. We are going to
            # do that manually so we can filter the warning.
            warnings.simplefilter("ignore", UserWarning)
            gs.tight_layout(fig)

        plt.savefig(outdir+"/elements_"+str(start/2)+"_"+name, dpi=600)

    # Next subject to number of bins
    # plots x-axis: bins, y_axis1: timings, y_axis2: speedup
    for start in range(0, 2):
        fig = plt.figure()
        start = start*max_elements_idx/2
        height_ratios = [0.5]
        for i in range(0, max_elements_idx/2):
            height_ratios.append(40)
        height_ratios.append(0.1)
        gs = gridspec.GridSpec(max_elements_idx/2+2, 2, width_ratios=[1,1],
                height_ratios=height_ratios)
        if used_device_data:
            plot_title = ('Histogram: Speedup and runtime with CPU and GPU\n'
                    'using already allocated device arrays')
        else:
            plot_title = 'Histogram: Speedup and runtime with CPU and GPU'
        plt.suptitle(plot_title, fontsize=16)
        for e in range(start, start+max_elements_idx/2):
            ax2 = plt.subplot(gs[2*(e-start)+2])
            seq_time2 = []
            running_time2_global = []
            running_time2_shared = []
            n_bins2 = []
            for d in range(0, len(timings)):
                for b in range(0, len(timings[d][n])):
                    n_bins2.append(pow(amount_of_bins[b], (d+1)))
                    seq_time2.append(timings[d][e][b][0][0])
                    running_time2_global.append(timings[d][e][b][0][1])
                    running_time2_shared.append(timings[d][e][b][0][2])
            create_subfig(seq_time2, running_time2_global, running_time2_shared,
                    np.asarray(n_bins2), ax2, width, 'Number of bins',
                    '(SP)', False, amount_of_elements[e])
            ax4 = plt.subplot(gs[2*(e-start)+3])
            seq_time4 = []
            running_time4_global = []
            running_time4_shared = []
            n_bins4 = []
            for d in range(0, len(timings)):
                for b in range(0, len(timings[d][n])):
                    n_bins4.append(pow(amount_of_bins[b], (d+1)))
                    seq_time4.append(timings[d][e][b][0][0])
                    running_time4_global.append(timings[d][e][b][0][1])
                    running_time4_shared.append(timings[d][e][b][0][2])
            create_subfig(seq_time4, running_time4_global, running_time4_shared,
                    np.asarray(n_bins4), ax4, width, 'Number of bins',
                    '(DP)', False, amount_of_elements[e])
        with warnings.catch_warnings():
            # This raises warnings since tight layout cannot
            # handle gridspec automatically. We are going to
            # do that manually so we can filter the warning.
            warnings.simplefilter("ignore", UserWarning)
            gs.tight_layout(fig)
        plt.savefig(outdir+"/bins_"+str(2*start/max_elements_idx)+"_"+name, dpi=600)


def create_subfig(seq_time1, running_time1_global, running_time1_shared,
        n_elements, ax1, width, x_name, title, not_using_bins, amount):
    """
    This method is called from plot_timings(). Subplots with timings and
    speedup are created. It handles the annotations and formatting.
    """
    if not_using_bins:
        plot_title = title + " with " + "{:.0E}".format(amount) + " bins"
    else:
        plot_title = title + " with " + "{:.0E}".format(amount) + " elements"
    ax1.set_title(plot_title, fontsize=10)
    ax1.grid(b=True, which='major')
    ax1.xaxis.set_major_formatter(FormatStrFormatter('%.2f'))
    ax1.yaxis.set_major_formatter(FormatStrFormatter('%.2f'))

    ax1.set_xscale('log')
    ax1.set_yscale('log')
    ax1_speedup = ax1.twinx()
    speedup1_global = []
    for i in range(0, len(running_time1_global)):
        speedup1_global.append(seq_time1[i]/running_time1_global[i])
    speedup1_shared = []
    for i in range(0, len(running_time1_shared)):
        speedup1_shared.append(seq_time1[i]/running_time1_shared[i])
    width_list = []
    for n in n_elements:
        width_list.append(n/3 * width)
    ax1_speedup.plot(n_elements, speedup1_global,
            color='black', marker="x", label='Speedup with global memory')
    ax1_speedup.plot(n_elements, speedup1_shared,
            color='black', linestyle='--',
            marker="o", fillstyle='none', label='Speedup with shared memory')
    ax1.bar(n_elements-width_list, running_time1_global,
            width = width_list, color=(0.7,0.7,0.8), align='edge',
            label="GPU global memory")
    ax1.bar(n_elements, running_time1_shared, width = width_list,
            color=(0.4,0.4,0.8), align='edge', label="GPU shared memory")
    ax1.bar(n_elements+width_list, seq_time1,
            width = width_list, color=(0.4,0.7,0.8), align='edge',
            label="CPU")
    global_approach = mpatches.Patch(color=(0.7,0.7,0.8),
            label='GPU global memory')
    shared_approach = mpatches.Patch(color=(0.4,0.4,0.8),
            label='GPU shared memory')
    cpu_approach = mpatches.Patch(color=(0.4,0.7,0.8), label='CPU')
    speed_up_global = mlines.Line2D([], [], color='black', marker="x",
            linestyle='-', label='Speedup with global memory')
    speed_up_shared = mlines.Line2D([], [], color='black', linestyle='--',
            marker="o", fillstyle='none', label='Speedup with shared memory')
    plt.legend(handles=[global_approach,shared_approach,cpu_approach,
            speed_up_global, speed_up_shared],
            bbox_to_anchor=(0.5, 0.0), loc=8,
            bbox_transform=plt.gcf().transFigure,  ncol=3, fontsize=10)
    ax1.set_xlabel(x_name, fontsize=8)
    ax1.set_ylabel('Running time in seconds', fontsize=8)
    ax1_speedup.set_ylabel('Speedup compared to CPU version', fontsize=8)
    for tick in ax1.xaxis.get_major_ticks():
        tick.label.set_fontsize(9)
    for tick in ax1.yaxis.get_major_ticks():
        tick.label.set_fontsize(9)
    for label in ax1_speedup.yaxis.get_majorticklabels():
        label.set_fontsize(9)
    plt.xlim(n_elements[0]-width_list[0]*2,
            n_elements[len(n_elements)-1]+width_list[len(width_list)-1]*2)


if __name__ == '__main__':
    """
    This is based on
    https://devblogs.nvidia.com/parallelforall/gpu-pro-tip-fast-histograms-using-shared-atomics-maxwell/
    http://parse.ele.tue.nl/system/attachments/10/original/GPGPU_High%20Performance%20Predictable%20Histogramming%20on%20GPUs.pdf?1314781744
    https://isaac.gelado.cat/sites/isaac.gelado.cat/files/publications/samos_2013_histogramming.pdf
    """
    # Do cool stuff
    parser = ArgumentParser(
    description=
            '''Run several tests for histogramming with a GPU.''',
    formatter_class=RawTextHelpFormatter)
    parser.add_argument('--full', action='store_true',
            help=
            '''Full test with comparison of numpy's histogramdd and GPU code
            with single and double precision and the GPU code with shared and
            global memory.''')
    parser.add_argument('--gpu-shared', action='store_true',
            help=
            '''Use GPU code with shared memory. If --gpu-both is set, then
            --gpu-shared will be ignored.''')
    parser.add_argument('--gpu-global', action='store_true',
            help=
            '''Use GPU code with global memory. If --gpu-both is set, then
            --gpu-global will be ignored.''')
    parser.add_argument('--gpu-both', action='store_true',
            help=
            '''Use GPU code with shared memory and global memory and compare
            both.''')
    parser.add_argument('--cpu', action='store_true',
            help=
            '''Use numpy's histogramdd.''')
    parser.add_argument('--all-precisions', action='store_true',
            help=
            '''Run all specified tests with double and single precision.''')
    parser.add_argument('-s', '--single-precision', action='store_true', help=
            '''Use single precision. If it is not set, use double precision.
            If --all-precisions is used, then -s will be ignored.''')
    parser.add_argument('-d', '--data', type=int, required=False,
            default=256*256, help=
            '''Define the number of elements in each dimension for the input
            data.''')
    parser.add_argument('--device-data', action='store_true',
            help=
            '''Use device arrays as input data.''')
    parser.add_argument('--dims', type=int, required=False, default=1,
            help=
            '''Define the number of dimensions for the input data and
            the histogram.''')
    parser.add_argument('-b', '--bins', type=int, required=False, default=256,
            help=
            '''Choose the number of bins for each dimension''')
    parser.add_argument('-w', '--weights', action='store_true',
            help=
            '''(Randomized) weights will be used on the histogram.''')
    parser.add_argument('--use-given-edges', action='store_true',
            help=
            '''Use calculated edges instead of calculating edges during
            histogramming.''')
    parser.add_argument('--outdir', metavar='DIR', type=str,
            help=
            '''Store all output plots to this directory. If
            they don't exist, the script will make them, including
            all subdirectories. If none is supplied no plots will
            be saved.''')
    parser.add_argument('--test', action='store_true',
            help=
            '''Make a test with all versions and print the timings.
            Do not make any other things.''')
    args = parser.parse_args()

    if args.single_precision and not args.all_precisions and not args.full:
        ftype = np.float32

    if args.outdir is not None:
        mkdir(args.outdir, warn=False)

    # TODO: add weights if called to do so
    weights = None
    #if args.weights:
    #    weights = create_weights(n_elements, n_dims, ftype=ftype)

    edges = None
    if args.use_given_edges:
        edges = create_edges(n_bins=args.bins, n_dims=args.dims,
                             ftype=ftype)

    if edges is None:
        edges = args.bins

    if args.test:
        mem = virtual_memory()
        available_memory = mem.available
        amount_of_elements = [1e8] #, 1e3, 1e4]

        # TODO: What is going on here? I suppose this kind of logic could be
        # used to limit the below-defined "all_bins" and "all_elements"
        # appropriately, but... not really clear how exactly to do so, and
        # probably depends upon ftype, etc. to do this correctly.
        max_elements = 0
        for i in amount_of_elements:
            if available_memory > i*8:
                max_elements = max_elements+1

        n_trials = 10
        timings = []

        all_dims = [1]
        all_elements = np.logspace(0, 6, 7)
        all_bins = np.logspace(0, 6, 7)
        all_ftypes = [np.float32, np.float64]

        for n_dims, n_elements, n_bins, ftype in product(
                all_dims, all_elements, all_bins, all_ftypes):
            n_elements = int(n_elements)
            n_bins = int(n_bins)

            info = OrderedDict([
                ('ftype', ftype.__name__),
                ('n_dims', n_dims),
                ('n_elements', n_elements),
                ('n_bins', n_bins),
            ])

            input_data, d_input_data = create_array(
                n_elements=n_elements,
                n_dims=n_dims,
                device_array=True,
                ftype=ftype
            )

            edges = None
            if args.use_given_edges:
                edges = create_edges(n_bins=n_bins,
                                     n_dims=n_dims,
                                     ftype=ftype)
            if edges is None:
                edges = n_bins

            # CPU
            tmp_timings = []
            for i in xrange(n_trials):
                start = timer()
                histogram_d_numpy, edges_d = np.histogramdd(
                    input_data, bins=edges, weights=weights
                )
                end = timer()
                tmp_timings.append(end - start)
            timings.append(
                record_timing(method='cpu', info=info, timings=tmp_timings)
            )

            # GPU global memory
            tmp_timings = []
            with gpu_hist.GPUHist(ftype=ftype) as histogrammer:
                for i in xrange(n_trials):
                    start = timer()
                    histogram_gpu_global, edges_gpu_global = histogrammer.get_hist(
                        sample=d_input_data, bins=edges, shared=False,
                        dims=args.dims, number_of_events=n_elements*n_dims
                    )
                    end = timer()
                    tmp_timings.append(end - start)
            timings.append(
                record_timing(method='gpu_global', info=info, timings=tmp_timings)
            )

            # GPU shared memory
            tmp_timings = []
            with gpu_hist.GPUHist(ftype=ftype) as histogrammer:
                for i in xrange(n_trials):
                    start = timer()
                    histogram_gpu_shared, edges_gpu_shared = histogrammer.get_hist(
                        sample=d_input_data, bins=edges, shared=True,
                        dims=args.dims, number_of_events=n_elements*n_dims
                    )
                    end = timer()
                    tmp_timings.append(end - start)
            timings.append(
                record_timing(method='gpu_shared', info=info, timings=tmp_timings)
            )

        if args.device_data:
            name = "test_device_data"
        else:
            name = "test_host_data"
        df = pd.DataFrame(timings)
        df.sort_values(by=['ftype', 'n_dims', 'n_elements', 'n_bins',
                           'method'], inplace=True)
        pd.set_option('display.max_rows', 500)
        pd.set_option('display.max_columns', 500)
        pd.set_option('display.width', 1000)
        print df

        if args.outdir is not None:
            df.to_csv(os.path.join(args.outdir, name + '.csv'))

            # TODO: make this compatible with Pandas DataFrame timings
            #plot_timings(timings=timings, outdir=args.outdir)

        sys.exit()

    if args.full:
        print("Starting full histogramming")

        # First with double precision
        with gpu_hist.GPUHist(ftype=ftype) as histogrammer:
            histogram_d_gpu_shared, edges_d_gpu_shared = histogrammer.get_hist(
                sample=d_input_data, bins=edges, shared=True,
                dims=args.dims, number_of_events=n_elements*n_dims
            )
            histogram_d_gpu_global, edges_d_gpu_global = histogrammer.get_hist(
                sample=d_input_data, bins=edges, shared=False,
                dims=args.dims, number_of_events=n_elements*n_dims
            )
        if edges is None:
            histogram_d_numpy, edges_d = np.histogramdd(input_data,
                                                        bins=args.bins,
                                                        weights=weights)
        else:
            histogram_d_numpy, edges_d = np.histogramdd(input_data, bins=edges,
                                                        weights=weights)
        # Next with single precision
        ftype = np.float32
        input_data, d_input_data = create_array(
            n_elements=n_elements,
            n_dims=d,
            device_array=args.device_data,
            ftype=ftype
        )
        with gpu_hist.GPUHist(ftype=ftype) as histogrammer:
            histogram_s_gpu_shared, edges_s_gpu_shared = histogrammer.get_hist(
                sample=d_input_data, bins=edges, shared=True,
                dims=args.dims, number_of_events=n_elements*n_dims
            )
            histogram_s_gpu_global, edges_s_gpu_global = histogrammer.get_hist(
                sample=d_input_data, bins=edges, shared=False,
                dims=args.dims, number_of_events=n_elements*n_dims
            )
        if edges is None:
            histogram_s_numpy, edges_s = np.histogramdd(input_data,
                    bins=args.bins, weights=weights)
        else:
            histogram_s_numpy, edges_s = np.histogramdd(input_data, bins=edges,
                    weights=weights)
        if args.outdir != None:
            plot_histogram(histogram_d_gpu_shared, edges_d_gpu_shared,
                    args.outdir, "GPU shared memory, double", args.bins)
            plot_histogram(histogram_d_gpu_global, edges_d_gpu_global,
                    args.outdir, "GPU global memory, double", args.bins)
            plot_histogram(histogram_d_numpy, edges_d, args.outdir,
                    "CPU, double", args.bins)
            plot_histogram(histogram_s_gpu_shared, edges_s_gpu_shared,
                    args.outdir, "GPU shared memory, single", args.bins)
            plot_histogram(histogram_s_gpu_global, edges_s_gpu_global,
                    args.outdir, "GPU global memory, single", args.bins)
            plot_histogram(histogram_s_numpy, edges_s, args.outdir,
                    "CPU, single", args.bins)
        sys.exit()

    if args.gpu_both:
        print("Starting histogramming on GPU only")
        # if not args.all_precisions and args.single_precision then this is
        # single precision. Hence the missing "d" or "s" in the name.
        with gpu_hist.GPUHist(ftype=ftype) as histogrammer:
            histogram_gpu_shared, edges_gpu_shared = histogrammer.get_hist(
                sample=d_input_data, bins=edges, shared=True,
                dims=args.dims, number_of_events=n_elements*n_dims
            )
        with gpu_hist.GPUHist(ftype=ftype) as histogrammer:
            histogram_gpu_global, edges_gpu_global = histogrammer.get_hist(
                sample=d_input_data, bins=edges, shared=False,
                dims=args.dims, number_of_events=n_elements*n_dims
            )
        if args.all_precisions:
            ftype = np.float32
            input_data, d_input_data = create_array(
                n_elements=n_elements,
                n_dims=d,
                device_array=args.device_data,
                ftype=ftype
            )
            with gpu_hist.GPUHist(ftype=ftype) as histogrammer:
                histogram_s_gpu_shared, edges_s_gpu_shared = histogrammer.get_hist(
                    sample=d_input_data, bins=edges, shared=True,
                    dims=args.dims, number_of_events=n_elements*n_dims
                )
                histogram_s_gpu_global, edges_s_gpu_global = histogrammer.get_hist(
                    sample=d_input_data, bins=edges, shared=False,
                    dims=args.dims, number_of_events=n_elements*n_dims
                )
            if args.outdir != None:
                plot_histogram(histogram_gpu_shared, edges_gpu_shared, args.outdir,
                        "GPU shared memory, double", args.bins)
                plot_histogram(histogram_gpu_global, edges_gpu_global, args.outdir,
                        "GPU global memory, double", args.bins)
                plot_histogram(histogram_s_gpu_shared, edges_s_gpu_shared,
                        args.outdir, "GPU shared memory, single", args.bins)
                plot_histogram(histogram_s_gpu_global, edges_s_gpu_global,
                        args.outdir, "GPU global memory, single", args.bins)
        elif args.outdir != None:
            name = ""
            if args.single_precision:
                name = "single"
            else:
                name = "double"
            plot_histogram(histogram_gpu_shared, edges_gpu_shared, args.outdir,
                    "GPU shared memory, " + name, args.bins)
            plot_histogram(histogram_gpu_global, edges_gpu_global, args.outdir,
                    "GPU global memory, " + name, args.bins)

    if args.gpu_shared and not args.gpu_both:
        print("Starting histogramming on GPU with shared memory")
        with gpu_hist.GPUHist(ftype=ftype) as histogrammer:
            histogram_gpu_shared, edges_gpu_shared = histogrammer.get_hist(
                sample=d_input_data, bins=edges, shared=True,
                dims=args.dims, number_of_events=n_elements*n_dims
            )
        if args.all_precisions:
            ftype = np.float32
            input_data, d_input_data = create_array(
                n_elements=n_elements,
                n_dims=d,
                device_array=args.device_data,
                ftype=ftype
            )
            with gpu_hist.GPUHist(ftype=ftype) as histogrammer:
                histogram_s_gpu_shared, edges_s_gpu_shared = histogrammer.get_hist(
                    sample=d_input_data, bins=edges, shared=True,
                    dims=args.dims, number_of_events=n_elements*n_dims
                )
            if args.outdir != None:
                plot_histogram(histogram_gpu_shared, edges_gpu_shared, args.outdir,
                        "GPU shared memory, double", args.bins)
                plot_histogram(histogram_s_gpu_shared, edges_s_gpu_shared,
                        args.outdir, "GPU shared memory, single", args.bins)
        elif args.outdir != None:
            name = ""
            if args.single_precision:
                name = "single"
            else:
                name = "double"
            plot_histogram(histogram_gpu_shared, edges_gpu_shared, args.outdir,
                    "GPU shared memory, " + name, args.bins)

    if args.gpu_global and not args.gpu_both:
        print("Starting histogramming on GPU with global memory")
        with gpu_hist.GPUHist(ftype=ftype) as histogrammer:
            histogram_gpu_global, edges_gpu_global = histogrammer.get_hist(
                sample=d_input_data, bins=edges, shared=False,
                dims=args.dims, number_of_events=n_elements*n_dims
            )
        if args.all_precisions:
            ftype = np.float32
            input_data, d_input_data = create_array(
                n_elements=n_elements,
                n_dims=d,
                device_array=args.device_data,
                ftype=ftype
            )
            with gpu_hist.GPUHist(ftype=ftype) as histogrammer:
                histogram_s_gpu_global, edges_s_gpu_global = histogrammer.get_hist(
                    sample=d_input_data, bins=edges, shared=False,
                    dims=args.dims, number_of_events=n_elements*n_dims
                )
            if args.outdir != None:
                plot_histogram(histogram_gpu_global, edges_gpu_global, args.outdir,
                        "GPU global memory, double", args.bins)
                plot_histogram(histogram_s_gpu_global, edges_s_gpu_global,
                        args.outdir, "GPU global memory, single", args.bins)
        elif args.outdir != None:
            name = ""
            if args.single_precision:
                name = "single"
            else:
                name = "double"
            plot_histogram(histogram_gpu_global, edges_gpu_global, args.outdir,
                    "GPU global memory, " + name, args.bins)

    if args.cpu:
        if edges is None:
            histogram_d_numpy, edges_d = np.histogramdd(input_data,
                    bins=args.bins, weights=weights)
        else:
            histogram_d_numpy, edges_d = np.histogramdd(input_data, bins=edges,
                    weights=weights)
        if args.all_precisions:
            ftype = np.float32
            input_data, d_input_data = create_array(
                n_elements=n_elements,
                n_dims=d,
                device_array=args.device_data,
                ftype=ftype
            )
            if edges is None:
                histogram_s_numpy, edges_s = np.histogramdd(input_data,
                        bins=args.bins, weights=weights)
            else:
                histogram_s_numpy, edges_s = np.histogramdd(input_data,
                        bins=edges, weights=weights)
        if args.outdir != None:
            plot_histogram(histogram_d_numpy, edges_d, args.outdir,
                    "CPU, double", args.bins)
            if args.all_precisions:
                plot_histogram(histogram_s_numpy, edges_s, args.outdir,
                        "CPU, single", args.bins)
