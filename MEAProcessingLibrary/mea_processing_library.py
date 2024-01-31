#general imports
import logging
import os
import glob
import shutil
import json

#spikeinterface imports
import spikeinterface
import spikeinterface.full as si
import spikeinterface.extractors as se
import spikeinterface.preprocessing as spre
import spikeinterface.sorters as ss
import spikeinterface.core as sc
import spikeinterface.postprocessing as sp
import spikeinterface.preprocessing as spre

#Logger Setup
#Create a logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Create handlers
stream_handler = logging.StreamHandler()  # logs to console
#file_handler = logging.FileHandler('file.log')  # logs to a file

# Set level of handlers
stream_handler.setLevel(logging.DEBUG)
#file_handler.setLevel(logging.ERROR)

# Add handlers to the logger
logger.addHandler(stream_handler)
#logger.addHandler(file_handler)

# Create formatters and add it to handlers
#formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
stream_handler.setFormatter(formatter)

def extract_raw_h5_filepaths(directories):
    """
    This function finds all files named 'data.raw.h5' in the given directories and their subdirectories.

    Parameters:
    directories: The list of directories to search for 'data.raw.h5' files.

    Returns:
    h5_dirs: The list of paths to the found 'data.raw.h5' files.
    """
    logger.info(f"Extracting .h5 file paths from directories:")
    h5_dirs = []
    for directory in directories:
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file == "data.raw.h5":
                    h5_dirs.append(os.path.join(root, file))
    return h5_dirs

import os

def extract_recording_details(h5_dirs):
    """
    This function extracts details about each recording from the given h5 directories.
    The details include the file path, run ID, scan type, chip ID, and recording date.

    Parameters:
    h5_dirs: The list of h5 directories.

    Returns:
    records: The list of dictionaries, where each dictionary contains details about a recording.
    """
    # If h5_dirs is a string, convert it to a list with a single element
    if isinstance(h5_dirs, str):
        h5_dirs = [h5_dirs]

    logger.info(f"Extracting recording details from h5 directories:")
    records = []
    for h5_dir in h5_dirs:
        parent_dir = os.path.dirname(h5_dir)
        runID = os.path.basename(parent_dir)

        grandparent_dir = os.path.dirname(parent_dir)
        scan_type = os.path.basename(grandparent_dir)

        great_grandparent_dir = os.path.dirname(grandparent_dir)
        chipID = os.path.basename(great_grandparent_dir)

        ggg_dir = os.path.dirname(great_grandparent_dir)
        date = os.path.basename(ggg_dir)

        record = {'h5_file_path': h5_dir, 
                  'runID': runID, 
                  'scanType': scan_type, 
                  'chipID': chipID,
                  'date': date}
        records.append(record)

    return records

def test_continuity(h5_file_path, verbose=False):
    """
    This function tests the continuity of a given h5 file by attempting to read recordings from the file until an error occurs.
    It also counts the number of successful reads (recordings).

    If the verbose flag is set to True, the function logs the number of recordings detected.

    If a recording is an exception object, an error has occurred. The function logs the error and appends False to a list.
    If the recording is successfully read, the function logs the success and appends True to the list.

    After attempting to read all recordings, the function checks if all items in the list are True. If they are, all recordings are continuous, and the function logs this and returns True. If not all items are True, the data is not continuous, and the function logs this and returns False.

    Parameters:
    h5_file_path (str): The path to the h5 file to read from.
    verbose (bool): If True, log detailed output. Default is False.

    Returns:
    bool: True if all recordings are continuous, False otherwise.
    """
    logger.info(f"Testing continuity of {h5_file_path}:")
    stream_count, rec_count = count_wells_and_recs(h5_file_path, verbose = verbose)
    if stream_count == 0:
        logger.error("No recordings detected, none are continuous.")
        return False  
    #This part of the function might be entirely unnecessary:
    TrueorFalse_list = []
    for stream_num in range(stream_count):
        for rec_num in range(rec_count[stream_num]):
            try: recording, rec_name, stream_id = get_data_maxwell(h5_file_path, rec_num = rec_num, well_num = stream_num, verbose = verbose)
            except: recording, rec_name, stream_id = get_data_maxwell(h5_file_path, rec_num = rec_num, verbose = verbose)
            if isinstance(recording, BaseException):
                e = recording
                if "Unable to open object (object 'routed' doesn't exist)" in str(e):
                    logger.error("This error indicates that 'RecordSpikesOnly' was active during this recording. Data are not continuous.")
                else:
                    logger.error("Unknown error")
                    logger.error(e)
                    logger.error("This error is unexpected. Please check the error message and try to resolve it.")
                TrueorFalse_list.append(False)
            else:
                logger.info(f"Successfully read Stream ID: {stream_id}, Recording: {rec_name}, indicating continuity.")
                TrueorFalse_list.append(True)
    #if all items in TrueorFalse_list are True, then the data is continuous
    if all(TrueorFalse_list):
        logger.info("All recordings are continuous.")
        return True
    else:
        logger.error("Data are not continuous.")
        return False
    #This part of the function might be entirely unnecessary:


def count_wells_and_recs(h5_file_path, verbose=False):
    """
    This function counts the number of wells (stream IDs) in a given file path by attempting to read recordings 
    from the file until an error occurs. It also counts the number of successful reads (recordings) for each stream ID.

    If the verbose flag is set to True, the function logs the stream ID and the number of recordings detected 
    for each stream ID.

    If the number of recordings is not consistent across all stream IDs, the function logs a warning and 
    the range of recordings detected. Otherwise, it logs the common number of recordings per stream ID.

    Finally, the function returns the total number of stream IDs detected and the number of recording segments 
    per stream ID.

    Parameters:
    h5_file_path (str): The path to the file to read from.
    verbose (bool): If True, log detailed output. Default is False.

    Returns:
    tuple: 
    (1) number of stream IDs detected 
    (2) and an array containing number of recording segments per stream ID.
    """
    logger.info(f"Counting wells and recordings in {h5_file_path}:")
    h5_details = extract_recording_details(h5_file_path)
    scanType = h5_details[0]['scanType']
    logger.info(f"Scan Type: {scanType}")
    stream_ids = []
    rec_counts = []
    stream_id = 0
    rec_count = 0

    #Check if MaxOne or MaxTwo
    stream_id_str = f'well{stream_id:03}'
    rec_name_str = f'rec{rec_count:04}'
    try: 
        recording = se.read_maxwell(h5_file_path, rec_name=rec_name_str, stream_id=stream_id_str)
        MaxID = 2
    except:
        try:
            recording = se.read_maxwell(h5_file_path, rec_name=rec_name_str)
            MaxID = 1
        except:
            logger.error("Error: Unable to read recording. Cannot identify as MaxOne or MaxTwo.")
            return 0, 0
    
    if MaxID == 1:
        logger.info("MaxOne Detected.")    
        #Maxone
        while True:
            try:
                rec_name_str = f'rec{rec_count:04}'
                recording = se.read_maxwell(h5_file_path, rec_name=rec_name_str)
                #When counting recordings, Network scans dont require a rec_name and will loop endlessly if not handled
                if "Network" in h5_file_path:
                    assert rec_count == 0, "rec_count should be 0 before incrementing when 'network' is in h5_file_path"
                    rec_count = 1
                else:
                    rec_count += 1
            except:            
                rec_counts.append(rec_count)
                if rec_count == 0:
                    break            
                if verbose:
                    logger.info(f"{rec_count} recordings detected.")
        return 1, rec_counts if rec_counts else 0

    elif MaxID == 2:
        logger.info("MaxTwo Detected.")
        #MaxTwo
        while True:
            try:
                stream_id_str = f'well{stream_id:03}'
                rec_name_str = f'rec{rec_count:04}'
                recording = se.read_maxwell(h5_file_path, rec_name=rec_name_str, stream_id=stream_id_str)
                #When counting recordings, Network scans dont require a rec_name and will loop endlessly if not handled
                if "Network" in h5_file_path:
                    assert rec_count == 0, "rec_count should be 0 before incrementing when 'network' is in h5_file_path"
                    rec_count = 1
                else:
                    rec_count += 1
            except:            
                rec_counts.append(rec_count)
                if rec_count == 0:
                    break            
                stream_ids.append(stream_id_str)
                if verbose:
                    logger.info(f"Stream ID: {stream_id_str}, {rec_count} recordings detected.")
                rec_count = 0
                stream_id += 1
        if len(set(rec_counts)) > 1: 
            logger.error(f"Warning: The number of recordings is not consistent across all stream IDs. Range: {min(rec_counts)}-{max(rec_counts)}")
        else: 
            logger.info(f"Recordings per Stream ID: {rec_counts[0]}")
        logger.info(f"Stream IDs Detected: {len(stream_ids)}")
    
        return len(stream_ids), rec_counts if rec_counts else 0
    
def count_recording_segments(recording, verbose=True):
    """
    This function counts the number of recording segments in a given RecordingExtractor object by using the 
    get_num_segments method. 

    If the verbose flag is set to True, the function prints the number of recording segments detected.

    Finally, the function returns the total number of recording segments detected.

    Parameters:
    recording (RecordingExtractor): The RecordingExtractor object to count segments from.
    verbose (bool): If True, print detailed output. Default is True.

    Returns:
    int: The number of recording segments detected.
    """
    logger.info(f"Counting Segments in Recording:")
    num_segments = recording.get_num_segments()

    if verbose:
        logger.info(f"Number of segments in the recording: {num_segments}")

    return num_segments

def get_data_maxwell(h5_file_path, rec_num, well_num = None, verbose = False):
    """
    This function reads a recording from a given file path using the read_maxwell method from the RecordingExtractor object. 

    The function constructs the recording name and stream ID based on the provided recording number and well number. 
    If no well number is provided, the stream ID is set to None.

    If the verbose flag is set to True, the function prints detailed output.

    If an exception occurs while reading the recording, the function prints an error log and returns None for the recording.

    Parameters:
    file_path (str): The path to the file to read from.
    rec_num (int): The number of the recording to read from.
    well_num (int, optional): The number of the well to read from. Default is None.
    verbose (bool): If True, print detailed output. Default is False.

    Returns:
    tuple: A tuple containing the RecordingExtractor object, the recording name, and the stream ID. If an exception occurs, the RecordingExtractor object is None.
    """
    logger.info(f"Extracting Recording Object from h5_file:")
    rec_num =  str(rec_num).zfill(4)
    rec_name = 'rec' + rec_num
    stream_id='well' + str(well_num).zfill(3) if well_num is not None else None
    recording = None
    try:
        if well_num is not None:
            recording = se.read_maxwell(h5_file_path,rec_name=rec_name, stream_id=stream_id)
            if verbose: logger.info(f"Successfully read recording from well {well_num}.")
        else:
            recording = se.read_maxwell(h5_file_path,rec_name=rec_name)
            if verbose: logger.info("Successfully read recording.")
    except Exception as e:
        logger.error(f"Failed to read recording. Exception: {e}")
        return e, rec_name, stream_id
    return recording, rec_name, stream_id

def merge_mea_recording_segments(recordings, mode='concatenate'):
    """
    recordings: List of recording objects
    mode: Either 'append' or 'concatenate'. Determines how the recordings are merged.
    """
    logger.info(f"Merging Recording Objects ({mode}):")
    try:
        #(untested) for same set of channels in each recording, generate list of segments
        if mode == 'append':
            merged_recording = spikeinterface.append_recordings(recordings)
        #(untested) for same set of channels in each recording, generate single segment
        elif mode == 'concatenate':
            merged_recording = spikeinterface.concatenate_recordings(recordings)
        #for different sets of channels in each recording
        elif mode == 'aggregate':
            merged_recording = si.aggregate_channels(recordings)
        else:
            logger.error("Invalid mode. Must be either 'append' or 'concatenate'.")
    except Exception as e:
        merged_recording = None
        logger.error(f"Failed to merge recordings. Exception: {e}")

    return merged_recording

def merge_sortings(sortings, mode='aggregate'):
    """
    recordings: List of recording objects
    mode: Either 'append' or 'concatenate'. Determines how the recordings are merged.
    """
    logger.info(f"Merging Sorting Objects ({mode}):")
    try:
        #for different sets of channels in each recording
        if mode == 'aggregate':
            merged_sorting = si.aggregate_units(sortings)
        else:
            logger.error("Invalid mode. Must be either 'append' or 'concatenate'.")
    except Exception as e:
        merged_sorting = None
        logger.error(f"Failed to merge sortings. Exception: {e}")

    return merged_sorting

def get_channel_recording_stats(recording):
    """
    This function retrieves various statistics about a given recording.

    Parameters:
    recording: The recording object to get statistics for.

    Returns:
    fs: The sampling frequency of the recording.
    num_chan: The number of channels in the recording.
    channel_ids: The IDs of the channels in the recording.
    total_recording: The total duration of the recording in seconds.
    """
    logger.info(f"Getting Channel Recording Characteristics:")
    channel_ids = recording.get_channel_ids()
    fs = recording.get_sampling_frequency()
    num_chan = recording.get_num_channels()
    num_seg = recording.get_num_segments()
    total_recording = recording.get_total_duration()

    logger.info(f'Sampling frequency: {fs}')
    logger.info(f'Number of channels: {num_chan}')
    logger.info(f'Number of segments: {num_seg}')
    logger.info(f"Total recording duration: {total_recording} s")

    return fs, num_chan, channel_ids, total_recording

def preprocess_recording(recording): #AW25Jan24 - some hardcoded stuff here, discuss with Mandar later
    """
    This function performs preprocessing on a given recording. The preprocessing steps include:
    1. Bandpass filtering: This removes frequencies outside the range of 300 Hz to half the sampling frequency minus 1.
    2. Common median referencing (CMR): This is a technique used to reduce common noise sources. It works by subtracting the median of all channels from each individual channel.

    Parameters:
    recording: The recording object to preprocess.

    Returns:
    recording_cmr: The preprocessed recording object. It has been bandpass filtered and common median referenced.
    """
    recording_bp = spre.bandpass_filter(recording, freq_min=300, freq_max=(recording.sampling_frequency/2)-1)
    recording_cmr = spre.common_reference(recording_bp, reference='global', operator='median')
    recording_cmr.annotate(is_filtered=True)

    return recording_cmr

def prepare_recordings_for_merge(recording_list):
    """
    This function prepares a list of recordings for merging by getting a chunk of each recording and preprocessing it.
    It then performs quality checks to ensure that all recordings have the same sampling frequency, number of segments, data type, and number of samples.

    Parameters:
    recording_list: The list of recording objects to prepare for merging.

    Returns:
    recordings_to_merge: The list of preprocessed chunks of the recordings.
    """
    recordings_to_merge = []
    for recording in recording_list:
        # Get the recording statistics such as sampling frequency, number of channels, channel IDs, and total recording time
        fs, num_chan, channel_ids, total_rec_time = get_channel_recording_stats(recording)

        # Round the total recording time to the nearest whole number
        rounded_total_rec_time = round(total_rec_time)
        if total_rec_time > rounded_total_rec_time:
            time_in_s = rounded_total_rec_time
        else:
            time_in_s = total_rec_time

        # Define the start and end times for the recording chunk
        time_start = 0
        time_end = time_start + time_in_s

        # Get a chunk of the recording based on the start and end times and preprocess it
        recording_chunk = recording.frame_slice(start_frame=int(time_start * fs), end_frame=int(time_end * fs))
        recording_chunk = preprocess_recording(recording_chunk)
        recordings_to_merge.append(recording_chunk)

    # Quality checks
    fs = recordings_to_merge[0].get_sampling_frequency()
    num_segments = recordings_to_merge[0].get_num_segments()
    dtype = recordings_to_merge[0].get_dtype()

    ok1 = all(fs == rec.get_sampling_frequency() for rec in recordings_to_merge)
    ok2 = all(num_segments == rec.get_num_segments() for rec in recordings_to_merge)
    ok3 = all(dtype == rec.get_dtype() for rec in recordings_to_merge)
    ok4 = True
    for i_seg in range(num_segments):
        num_samples = recordings_to_merge[0].get_num_samples(i_seg)
        ok4 = all(num_samples == rec.get_num_samples(i_seg) for rec in recordings_to_merge)
        if not ok4:
            break

    if not (ok1 and ok2 and ok3 and ok4):
        raise ValueError("Recordings don't have the same sampling_frequency/num_segments/dtype/num samples")

    return recordings_to_merge

def preprocess_single_recording(recording):
    """
    This function prepares a single recording for merging by getting a chunk of the recording and preprocessing it.

    Parameters:
    recording: The recording object to prepare for merging.

    Returns:
    recording_chunk: The preprocessed chunk of the recording.
    """
    # Get the recording statistics such as sampling frequency, number of channels, channel IDs, and total recording time
    fs, num_chan, channel_ids, total_rec_time = get_channel_recording_stats(recording)

    # Round the total recording time to the nearest whole number
    rounded_total_rec_time = round(total_rec_time)
    if total_rec_time > rounded_total_rec_time:
        time_in_s = rounded_total_rec_time
    else:
        time_in_s = total_rec_time

    # Define the start and end times for the recording chunk
    time_start = 0
    time_end = time_start + time_in_s

    # Get a chunk of the recording based on the start and end times and preprocess it
    recording_chunk = recording.frame_slice(start_frame=int(time_start * fs), end_frame=int(time_end * fs))
    recording_chunk = preprocess_recording(recording_chunk)

    return recording_chunk

def run_kilosort2_docker_image(recording, chunk_duration, output_folder, docker_image= "spikeinterface/kilosort2-compiled-base:latest",verbose=False):
    default_KS2_params = ss.Kilosort2Sorter.default_params()
    default_KS3_params = ss.Kilosort3Sorter.default_params()
    # Assume `recording` is your original recording
    sampling_rate = recording.get_sampling_frequency()  # Get the sampling rate in Hz
    total_frames = recording.get_num_frames()  # Get the total number of frames

    # Let's say we want each chunk to be 10 seconds long
    #chunk_duration = 6  # Duration in seconds
    chunk_size = int(chunk_duration * sampling_rate)  # Convert duration to number of frames

    # Now you can use `chunk_size` in your loop as before
    for start_frame in range(0, total_frames, chunk_size):
        end_frame = min(start_frame + chunk_size, total_frames)
        chunk = recording.frame_slice(start_frame, end_frame)
        # Get the number of frames and channels in the chunk
        num_frames = chunk.get_num_frames()
        num_channels = chunk.get_num_channels()

        # Calculate the size of the chunk in bytes
        size_in_bytes = num_frames * num_channels * 4  # 4 bytes per data point

        # Convert the size to gigabytes
        #size_in_gigabytes = size_in_bytes / (1024 ** 3)

        # Print the size of the chunk
        #print(f"Chunk size: {size_in_gigabytes} GB")
        
        # Now you can pass `chunk` to `run_sorter` instead of the whole `recording`
        #sorting = ss.run_kilosort2(chunk, output_folder=output_folder, docker_image="spikeinterface/kilosort2-compiled-base:latest", verbose=verbose, **default_KS2_params)
        # Now you can pass `chunk` to `run_sorter` instead of the whole `recording`
        #sorting = ss.run_kilosort3(chunk, output_folder=output_folder, docker_image="spikeinterface/kilosort3-compiled-base:latest", verbose=verbose, **default_KS3_params)
    sorting = ss.run_kilosort2(recording, output_folder=output_folder, docker_image="spikeinterface/kilosort2-compiled-base:latest", verbose=verbose, **default_KS2_params)
    return sorting

def extract_waveforms(recording,sorting,folder, load_if_exists = False, n_jobs = 4, sparse = True):
    job_kwargs = dict(n_jobs=n_jobs, chunk_duration="1s", progress_bar=True)
    #waveforms = si.extract_waveforms(recording,sorting_KS3,folder=folder,overwrite=True,**job_kwargs)
    waveforms = si.extract_waveforms(recording,sorting,folder=folder,overwrite=True, load_if_exists=load_if_exists, sparse = sparse, ms_before=1., ms_after=2.,allow_unfiltered=True,**job_kwargs)
    return waveforms


def generate_waveform_extractor_unit_by_unit(recording,sorting,folder, n_jobs = 4, sparse = True, load_if_exists = False):
    
    def flex_load_waveforms(unit_ids, folder, tot_num_units):        

        def check_extraction_status(unit_range_folder, unit_waveforms):
            extraction_info_file = unit_range_folder + "/extraction_info.json"
            # Check if the extraction info file exists
            if os.path.exists(extraction_info_file):
                with open(extraction_info_file, "r") as json_file:
                    extraction_info = json.load(json_file)
                    if extraction_info["status"] == "extraction successful":
                        logger.info(f"Extraction for units {unit_range[0]} to {unit_range[-1]} was successful")
                    else:
                        raise Exception("Extraction was not successful")
            else:
                raise Exception("Extraction info file does not exist")
            if unit_waveforms.get_num_segments() == 0:
                raise Exception("Waveforms are empty")
            return unit_waveforms
        
        unit_id = unit_ids[0]
        while unit_id in unit_ids:
            # Try to load the widest range of units first
            for j in range(tot_num_units, unit_id, -1):
                unit_range_folder = folder + f"_unit_by_unit_temp/units_{unit_id}_to_{j}"
                if os.path.exists(unit_range_folder):
                    try:
                        unit_waveforms = si.load_waveforms(unit_range_folder)
                        # Extraction quality testing
                        check_extraction_status(unit_range_folder, unit_waveforms)
                        logger.info(f"Waveforms for units {unit_id} to {j} loaded from {unit_range_folder}")
                        unit_id = j + 1  # Update the next unit in sequence                        
                        return unit_waveforms, unit_id
                    except:
                        pass  # If loading fails, try the next range
            else:
                # If no range works, try to load a single unit
                unit_folder = folder + f"_unit_by_unit_temp/unit_{unit_id}"
                if os.path.exists(unit_folder):
                    try:
                        unit_waveforms = si.load_waveforms(unit_folder)
                       # Extraction quality testing
                        check_extraction_status(unit_range_folder, unit_waveforms)      
                        logger.info(f"Waveform for unit {unit_id} loaded from {unit_folder}")
                        unit_id += 1  # Update the next unit in sequence
                        return unit_waveforms, unit_id
                    except:
                        raise Exception(f"Failed to load waveforms for unit {unit_id}")
                else:
                    raise Exception(f"No folder found for unit {unit_id}")
        return unit_waveforms, unit_id
    
    def extract_waveforms_from_unit_range(unit_range, recording, sorting, folder, sparse, job_kwargs):
        unit_range_folder = folder + f"_unit_by_unit_temp/units_{unit_range[0]}_to_{unit_range[-1]}"
        logger.info(f"Extracting waveforms for units {unit_range[0]} to {unit_range[-1]} to {unit_range_folder}")
        unit_sorting = sorting.select_units(unit_range)
        unit_waveforms = si.extract_waveforms(recording, unit_sorting, 
                                              folder=unit_range_folder, overwrite=True, 
                                              load_if_exists=False, sparse=sparse, 
                                              ms_before=1., ms_after=2., 
                                              allow_unfiltered=True, **job_kwargs)        
        # Create a JSON file to confirm successful extraction
        extraction_info = {
            "units": unit_range.tolist(),  # convert numpy array to list
            "folder": unit_range_folder,
            "status": "extraction successful"
        }
        with open(unit_range_folder + "/extraction_info.json", "w") as json_file:
            json.dump(extraction_info, json_file)
        logger.info(f"Waveforms extracted")
        return unit_waveforms
        
    logger.info(f"Extracting waveforms unit by unit:")
    # Create a WaveformExtractor
    job_kwargs = dict(n_jobs=n_jobs, chunk_duration="1s", progress_bar=True)

    try:
        # Load the waveform extractor
        waveform_extractor = spikeinterface.load_extractor(folder)

        # Get the unit IDs from the waveform extractor and the sorting
        we_unit_ids = waveform_extractor.get_unit_ids()
        sorting_unit_ids = sorting.get_unit_ids()

        # If the number of unit IDs is the same, return
        if len(we_unit_ids) == len(sorting_unit_ids):
            logger.info(f"Waveform extractor loaded")
            return waveform_extractor
    except:
        logger.info(f"Waveform extractor not found")
        pass   

    # Extract waveforms for each unit
    unit_folders = []
    #Choose the number of units to extract at a time
    units_per_extraction = n_jobs
    logger.info(f"Extracting waveforms for up to {units_per_extraction} units at a time")
    unit_ids = sorting.get_unit_ids()
    # Process the units in chunks of 10
    i = 0
    tot_num_units = len(unit_ids)
    logger.info(f"Total number of units: {tot_num_units}")
    while i < tot_num_units:
        # Select up to 10 units
        unit_range = unit_ids[i:i+units_per_extraction]           
        if load_if_exists:
            try:
                # Flexibly try to load the waveforms from the folder                
                unit_waveforms, unit_id = flex_load_waveforms(unit_range, folder, tot_num_units)
                #update i to the next unit in sequence
                i = unit_id
            except:
                unit_waveforms = extract_waveforms_from_unit_range(unit_range, recording, sorting, folder, sparse, job_kwargs)
                i += units_per_extraction
        else:
            unit_waveforms = extract_waveforms_from_unit_range(unit_range, recording, sorting, folder, sparse, job_kwargs)
            i += units_per_extraction
        
    #Generate a waveform extractor from full recording and sorting
    logger.info(f"Generating new waveform extractor template from full recording and sorting.")
    # Remove unit folders and all their contents
    if os.path.exists(folder):
        shutil.rmtree(folder)
    
    # Create a WaveformExtractor 
    waveform_extractor = sc.WaveformExtractor.create(
        recording, sorting, folder=folder, allow_unfiltered=True
    )

    # Set the parameters for the waveform extractor
    waveform_extractor.set_params(
        ms_before=1.,
        ms_after=2.,
        #allow_unfiltered=True,
    )
    
    #Create a waveforms folder at the same level as the unit folders
    waveforms_folder = folder + "/waveforms"
    if not os.path.exists(waveforms_folder):
        os.makedirs(waveforms_folder)

    logger.info(f"Copying and merging waveforms folders from unit folders to template folder.")
    # from all unit_folder in unit_folders, move and merge the waveforms folder with higher waveforms folder we just created
    for unit_folder in unit_folders:
        unit_waveforms_folder = unit_folder + "/waveforms"
        if os.path.exists(unit_waveforms_folder):
            # Get the unit ID from the unit folder name
            unit_id = os.path.basename(unit_folder).split('_')[1]

            # Copy the sampled_index_i.npy and waveforms_i.npy files
            for old_name in glob.glob(unit_waveforms_folder + "/sampled_index_*.npy"):
                new_name = os.path.join(waveforms_folder, os.path.basename(old_name))
                shutil.copy(old_name, new_name)

            for old_name in glob.glob(unit_waveforms_folder + "/waveforms_*.npy"):
                new_name = os.path.join(waveforms_folder, os.path.basename(old_name))
                shutil.copy(old_name, new_name)
        
        # Copy the params.json file if it doesn't exist in the destination folder
        if not os.path.exists(folder + "/params.json"):
            shutil.copy(os.path.join(unit_folder, "params.json"), folder)
    logger.info(f"Unit waveforms copied. Full waveform extractor generated.")
    
    logger.info(f"Deleting temporary unit folders.")
    # Remove unit folders and all their contents
    temp_units_folder = folder + f"_unit_by_unit_temp"
    shutil.rmtree(temp_units_folder)
    logger.info(f"Temporary unit folder {temp_units_folder} deleted.")

    # Load the waveforms from folder
    waveform_extractor = si.load_waveforms(folder)
    
    #Add processing to mimic typical waveform extraction
    waveform_extractor.get_all_templates(mode = 'average')
    #spikeinterface.core.compute_sparsity(waveform_extractor)

    # Save the waveform extractor
    waveform_extractor.save(folder)

    return waveform_extractor

