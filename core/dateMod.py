# This is a datetime module for handling datetime
# calculations in the forcing engine.
from core import errMod
import datetime
import math

def calculate_lookback_window(ConfigOptions):
    """
    Calculate the beginning, ending datetime variables
    for a look-back period. Also calculate the processing
    time window delta value.
    :param ConfigOptions: Abstract class holding job information.
    :return: Updated abstract class with updated datetime variables.
    """
    # First calculate the current time in UTC.
    dCurrentUtc = datetime.datetime.utcnow()

    # Next, subtract the lookup window (specified in minutes) to get a crude window
    # of processing.
    dLookback = dCurrentUtc - datetime.timedelta(seconds=60*ConfigOptions.look_back)

    # Determine the first forecast iteration that will be processed on this day
    # based on the forecast frequency and where in the day we are at.
    fcstStepTmp = math.ceil((dLookback.hour*60 + dLookback.minute)/ConfigOptions.fcst_freq)
    dLookTmp1 = datetime.datetime(dLookback.year,dLookback.month,dLookback.day)
    dLookTmp1 = dLookTmp1 + datetime.timedelta(seconds=60*ConfigOptions.fcst_freq*fcstStepTmp)

    # If we are offsetting the forecasts, apply here.
    if ConfigOptions.fcst_shift > 0:
        dLookTmp1 = dLookTmp1 + datetime.timedelta(seconds=60*ConfigOptions.fcst_shift)

    ConfigOptions.b_date_proc = dLookTmp1


    # Now calculate the end of the processing window based on the time from the
    # beginning of the processing window.
    dtTmp = dCurrentUtc - ConfigOptions.b_date_proc
    nFcstSteps = math.floor((dtTmp.days*1440+dtTmp.seconds/60.0)/ConfigOptions.fcst_freq)
    ConfigOptions.nFcsts = int(nFcstSteps) + 1
    ConfigOptions.e_date_proc = ConfigOptions.b_date_proc + datetime.timedelta(seconds=nFcstSteps*ConfigOptions.fcst_freq*60)

def find_gfs_neighbors(input_forcings,ConfigOptions,dCurrent,MpiConfg):
    """
    Function to calcualte the previous and after GFS cycles based on the current timestep.
    :param input_forcings:
    :param ConfigOptions:
    :return:
    """
    if MpiConfg.rank == 0:
        if input_forcings.keyValue == 9:
            print("PROCESSING 0.25 Degree GFS")
        if input_forcings.keyValue == 3:
            print("PROCESSING Production GFS")

    # First calculate how the GFS files are structured based on our current processing date.
    # This will change in the future, and should be modified as the GFS system evolves.
    if dCurrent >= datetime.datetime(2018,10,1):
        gfsOutHorizons = [120, 240, 384]
        gfsOutFreq = {
            120: 60,
            240: 180,
            384: 720
        }
        gfsPrecipDelineators = {
            120: [360,60],
            240: [360,180],
            284: [720,720]
        }
    else:
        gfsOutHorizons = [120, 240, 384]
        gfsOutFreq = {
            120: 60,
            240: 180,
            384: 720
        }
        gfsPrecipDelineators = {
            120: [360, 60],
            240: [360, 180],
            284: [720, 720]
        }

    # If the user has specified a forcing horizon that is greater than what
    # is available here, return an error.
    if (input_forcings.userFcstHorizon+input_forcings.userCycleOffset)/60.0 > max(gfsOutHorizons):
        ConfigOptions.errMsg = "User has specified a GFS forecast horizon " \
                               "that is greater than maximum allowed hours of: " \
                               + str(max(gfsOutHorizons))
        print(ConfigOptions.errMsg)
        raise Exception

    # First determine if we need a previous file or not. For hourly files,
    # only need the previous file if it's not the first hour after a new GFS cycle
    # (I.E. 7z, 13z, 19z, 1z). Any other hourly timestep requires the previous hourly data
    # (I.E. 8z needs 7z file). For 3-hourly files, we will look for files for the previous
    # three hours and next three hourly output. For example, a timestep that falls 125 hours
    # after the beginning of the GFS cycle will require data from the f123 file and 126 file.
    # For any files after 240 hours out from the beginning of a GFS forecast cycle, the intervals
    # move to 12 hours.

    # First find the current GFS forecast cycle that we are using.
    currentGfsCycle = ConfigOptions.current_fcst_cycle - \
                      datetime.timedelta(seconds=
                                         (input_forcings.userCycleOffset)*60.0)
    if MpiConfg.rank == 0:
        print("CURRENT GFS CYCLE BEING USED = " + currentGfsCycle.strftime('%Y-%m-%d %H'))

    # Calculate the current forecast hour within this GFS cycle.
    dtTmp = dCurrent - currentGfsCycle
    currentGfsHour = int(dtTmp.days*24) + int(dtTmp.seconds/3600.0)
    if MpiConfg.rank == 0:
        print("Current GFS Forecast Hour = " + str(currentGfsHour))

    # Calculate the GFS output frequency based on our current GFS forecast hour.
    for horizonTmp in gfsOutHorizons:
        if currentGfsHour <= horizonTmp:
            currentGfsFreq = gfsOutFreq[horizonTmp]
            break
    if MpiConfg.rank == 0:
        print("Current GFS output frequency = " + str(currentGfsFreq))

    # Calculate the previous file to process.
    minSinceLastOutput = (currentGfsHour*60)%currentGfsFreq
    #print(currentGfsHour)
    #print(currentGfsFreq)
    #print(minSinceLastOutput)
    if minSinceLastOutput == 0:
        minSinceLastOutput = currentGfsFreq
        #currentGfsHour = currentGfsHour
        #previousGfsHour = currentGfsHour - int(currentGfsFreq/60.0)
    prevGfsDate = dCurrent - \
                  datetime.timedelta(seconds=minSinceLastOutput*60)
    #print(prevGfsDate)
    if minSinceLastOutput == currentGfsFreq:
        minUntilNextOutput = 0
    else:
        minUntilNextOutput = currentGfsFreq - minSinceLastOutput
    nextGfsDate = dCurrent + datetime.timedelta(seconds=minUntilNextOutput*60)
    #print(nextGfsDate)

    # Calculate the output forecast hours needed based on the prev/next dates.
    dtTmp = nextGfsDate - currentGfsCycle
    #print(currentGfsCycle)
    nextGfsForecastHour = int(dtTmp.days*24.0) + int(dtTmp.seconds/3600.0)
    #print(nextGfsForecastHour)
    input_forcings.fcst_hour2 = nextGfsForecastHour
    dtTmp = prevGfsDate - currentGfsCycle
    prevGfsForecastHour = int(dtTmp.days*24.0) + int(dtTmp.seconds/3600.0)
    #print(prevGfsForecastHour)
    input_forcings.fcst_hour1 = prevGfsForecastHour
    # If we are on the first GFS forecast hour (1), and we have calculated the previous forecast
    # hour to be 0, simply set both hours to be 1. Hour 0 will not produce the fields we need, and
    # no interpolation is required.
    if prevGfsForecastHour == 0:
        prevGfsForecastHour = 1

    # Calculate expected file paths.
    tmpFile1 = input_forcings.inDir + '/gfs.' + \
        currentGfsCycle.strftime('%Y%m%d%H') + "/gfs.t" + \
        currentGfsCycle.strftime('%H') + 'z.sfluxgrbf' + \
        str(prevGfsForecastHour).zfill(2) + '.grib2'
    #print(tmpFile1)
    tmpFile2 = input_forcings.inDir + '/gfs.' + \
        currentGfsCycle.strftime('%Y%m%d%H') + "/gfs.t" + \
        currentGfsCycle.strftime('%H') + 'z.sfluxgrbf' + \
        str(nextGfsForecastHour).zfill(2) + '.grib2'
    #print(tmpFile2)

    # Check to see if files are already set. If not, then reset, grids and
    # regridding objects to communicate things need to be re-established.
    if input_forcings.file_in1 != tmpFile1 and input_forcings.file_in2 != tmpFile2:
        input_forcings.file_in1 = tmpFile1
        input_forcings.file_in2 = tmpFile2
        input_forcings.regridComplete = False
        # If we have shifted GFS windows, check to see if the former
        # 'next' GFS file is now the new 'previous' gfs file.
        # If so, simply reset the end of the GFS window
        # to be the new beginning of the next window.
        if input_forcings.file_in2 == tmpFile1:
            if ConfigOptions.current_output_step == 1:
                if MpiConfg.rank == 0:
                    print('We are on the first output timestep.')
                input_forcings.regridded_forcings1 = None
                input_forcings.regridded_forcings2 = None
            else:
                # The GFS window has shifted. Reset fields 2 to
                # be fields 1.
                input_forcings.regridded_forcings1[:,:,:] = input_forcings.regridded_forcings2[:,:,:]