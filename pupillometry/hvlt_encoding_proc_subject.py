# -*- coding: utf-8 -*-
"""
Created on Fri Sep 16 12:00:45 2016

@author: jelman

This script takes Tobii .gazedata file from HVLT as input. It first performs 
interpolation and filtering, Then peristimulus timecourses are created for 
target and standard trials after baselining. Trial-level data 
and average PSTC waveforms data are output for further group processing using 
(i.e., with oddball_proc_group.py). 

Some procedures and parameters adapted from:
Jackson, I. and Sirois, S. (2009), Infant cognition: going full factorial 
    with pupil dilation. Developmental Science, 12: 670-679. 
    doi:10.1111/j.1467-7687.2008.00805.x

Hoeks, B. & Levelt, W.J.M. Behavior Research Methods, Instruments, & 
    Computers (1993) 25: 16. https://doi.org/10.3758/BF03204445
"""

from __future__ import division, print_function, absolute_import
import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import pupil_utils
try:
    # for Python2
    import Tkinter as tkinter
    import tkFileDialog as filedialog
except ImportError:
    # for Python3
    import tkinter
    from tkinter import filedialog


def plot_trials(pupildf, fname):
    palette = sns.color_palette('muted',n_colors=len(pupildf['Trial'].unique()))
    p = sns.lineplot(data=pupildf, x="Timestamp",y="Dilation", hue="Trial", palette=palette,legend="brief")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plot_outname = pupil_utils.get_proc_outfile(fname, "_PupilPlot.png")
    p.figure.savefig(plot_outname)
    plt.close()
    
    
def clean_trials(trialevents):
    resampled_dict = {}
    for trial in trialevents.Trial.unique():
        rawtrial =  trialevents.loc[trialevents.Trial==trial]
        rawtrial = rawtrial.loc[(rawtrial.CurrentObject=='Ready')|(rawtrial.CurrentObject.str.contains('PlayWord'))]
        cleantrial = pupil_utils.deblink(rawtrial, pupilthresh_hi=4., pupilthresh_lo=1.5)
        cleantrial.loc[:,'Trial'] = cleantrial.Trial.astype('str')
        string_cols = ['Trial', 'CurrentObject']
        trial_resamp = pupil_utils.resamp_filt_data(cleantrial, filt_type='low', string_cols=string_cols)        
        baseline = trial_resamp.loc[trial_resamp.CurrentObject=="Ready","DiameterPupilLRFilt"].last("500ms").mean()
        trial_resamp['Baseline'] = baseline
        trial_resamp['Dilation'] = trial_resamp['DiameterPupilLRFilt'] - trial_resamp['Baseline']
        trial_resamp = trial_resamp[trial_resamp.CurrentObject.str.match("PlayWord")]
        trial_resamp.index = pd.DatetimeIndex((trial_resamp.index - trial_resamp.index[0]).astype(np.int64))
        resampled_dict[trial] = trial_resamp        
    dfresamp = pd.concat(resampled_dict, names=['Trial','Timestamp'])
    return dfresamp
    
def define_condition(trialdf):
    trialdf['Condition'] = np.where((trialdf.TETTime - trialdf.TETTime.iloc[0]) / 1000. > 1., 'Record', 'Ready')
    return trialdf


def get_trial_events(df):
    """
    Split data for each of the 3 trials. This requires splitting the dataframe
    based on consecutive rows where CurrentObject is blank. 

    """
    isnull = df.CurrentObject.isnull()
    partitions = (isnull != isnull.shift()).cumsum()
    gb = df[~isnull].groupby(partitions)
    trial_nums = range(1, len(gb.groups) + 1)
    dfs = pd.concat([group for name, group in gb], keys=trial_nums)
    trialevents = dfs.reset_index(level=1, drop=True)
    trialevents.index.name = 'Trial'
    trialevents = trialevents.reset_index()
    return trialevents

   
def proc_subject(filelist):
    """Given an infile of raw pupil data, saves out:
        1. Session level data with dilation data summarized for each trial
        2. Dataframe of average peristumulus timecourse for each condition
        3. Plot of average peristumulus timecourse for each condition
        4. Percent of samples with blinks """
    for fname in filelist:
        print('Processing {}'.format(fname))
        if (os.path.splitext(fname)[-1] == ".gazedata") | (os.path.splitext(fname)[-1] == ".csv"):
            df = pd.read_csv(fname, sep="\t")
        elif os.path.splitext(fname)[-1] == ".xlsx":
            df = pd.read_excel(fname)
        else: 
            raise IOError('Could not open {}'.format(fname))   
        subid = pupil_utils.get_subid(df['Subject'], fname)
        timepoint = pupil_utils.get_timepoint(df['Session'], fname)
        trialevents = get_trial_events(df)
        dfresamp = clean_trials(trialevents)
        dfresamp = dfresamp.reset_index(level='Trial', drop=True).reset_index()
        pupildf = dfresamp.groupby('Trial').apply(lambda x: x.resample('1s', on='Timestamp', closed='right', label='right').mean()).reset_index()
        pupilcols = ['Subject', 'Trial', 'Timestamp', 'Dilation',
                     'Baseline', 'DiameterPupilLRFilt', 'BlinksLR']
        pupildf = pupildf[pupilcols]
        # Set subject ID and session as (as type string)
        pupildf['Subject'] = subid
        pupildf['Session'] = timepoint      
        pupildf = pupildf[pupilcols].rename(columns={'DiameterPupilLRFilt':'Diameter',
                                         'BlinksLR':'BlinkPct'})
        pupildf.loc[:,'Timestamp'] = pupildf.Timestamp.dt.strftime('%H:%M:%S')
        pupil_outname = pupil_utils.get_proc_outfile(fname, '_ProcessedPupil.csv')
        pupildf.to_csv(pupil_outname, index=False)
        print('Writing processed data to {0}'.format(pupil_outname))
        plot_trials(pupildf, fname)

        #### Create data for 6 second blocks
        dfresamp6s = dfresamp.groupby('Trial').apply(lambda x: x.resample('6s', on='Timestamp', closed='right', label='right').mean())
        pupilcols = ['Subject', 'Trial', 'Timestamp', 'Dilation',
                     'Baseline', 'DiameterPupilLRFilt', 'BlinksLR']
        pupildf6s = dfresamp6s.reset_index()[pupilcols].sort_values(by=['Trial','Timestamp'])
        pupildf6s = pupildf6s[pupilcols].rename(columns={'DiameterPupilLRFilt':'Diameter',
                                         'BlinksLR':'BlinkPct'})
        # Set subject ID as (as type string)
        pupildf6s['Subject'] = subid
        pupildf6s['Session'] = timepoint      
        pupildf6s['Timestamp'] = pd.to_datetime(pupildf6s.Timestamp).dt.strftime('%H:%M:%S')
        pupil6s_outname = pupil_utils.get_proc_outfile(fname, '_ProcessedPupil_Quartiles.csv')
        'Writing quartile data to {0}'.format(pupil6s_outname)
        pupildf6s.to_csv(pupil6s_outname, index=False)

    
if __name__ == '__main__':
    if len(sys.argv) == 1:
        print('')
        print('USAGE: {} <raw pupil file> '.format(os.path.basename(sys.argv[0])))
        print('USAGE: {} <raw pupil file> '.format(os.path.basename(sys.argv[0])))
        print("""Processes single subject data from HVLT encoding task and outputs
              csv files for use in further group analysis. Takes eye tracker 
              data text file (*.gazedata) as input. Removes artifacts, filters, 
              and calculates dilation per 1sec.""")
        root = tkinter.Tk()
        root.withdraw()
        # Select files to process
        filelist = filedialog.askopenfilenames(parent=root,
                                              title='Choose HVLT Encoding pupil gazedata file to process')

        filelist = list(filelist)
        # Run script
        proc_subject(filelist)

    else:
        filelist = [os.path.abspath(f) for f in sys.argv[1:]]
        proc_subject(filelist)

