from datetime import datetime
import json
from getpass import getpass
import os
import re
from landsatlinks.eeapi import eeapi
from landsatlinks.parseargs import parse_cli_arguments
import landsatlinks.utils as utils


def main():
    # ==================================================================================================================
    # 1. Check input and set up variables
    args = parse_cli_arguments()

    # path to links
    if not os.access(os.path.dirname(args.results), os.W_OK):
        print("Error: Directory where results are supposed to be stored does not exists or is not writeable. Exiting.")
        exit(1)
    else:
        searchResultsPath = os.path.realpath(args.results)
    # dataset name
    sat_dict = {'TM': 'landsat_tm_c2_l1', 'ETM': 'landsat_etm_c2_l1', 'OLI': 'landsat_ot_c2_l1'}
    datasetName = sat_dict[args.satellite]
    # path to pathrow list
    prListPath = args.pathrowlist
    if not os.path.exists(prListPath):
        print("Error: PathRow list file does not exists. Check the filepath. Exiting.")
        exit(1)

    # date range
    dates = args.daterange.split(',')
    dateRe = re.compile('[0-9]{4}-[0-1][0-2]-[0-3][0-9]')
    for date in dates:
        if not dateRe.match(date):
            print('Error: Dates not provided in the format YYYY-MM-DD,YYY-MM-DD')
            exit(1)
    start, end = dates
    # cloud cover
    if args.cloudcover:
        minCC, maxCC = args.cloudcover.split(',')
    # seasonal filter
    seasonalFilter = list(args.months.split(','))
    # tier
    tier = args.tier


    # ==================================================================================================================
    # 2. Run
    # Login
    user = input("Enter your USGS EarthExplorer username: ")
    passwd = getpass("Enter your USGS EarthExplorer password: ")
    api = eeapi(user, passwd)

    try:
        prList = utils.load_tile_list(prListPath)
    except:
        print("Could not load path row list.")

    # First run: no results file in filesystem yet
    if not os.path.exists(searchResultsPath):
        sceneResponse = api.scene_search(dataset_name=datasetName,
                                         pr_list=prList,
                                         start=start, end=end, seasonal_filter=seasonalFilter,
                                         min_cc=minCC, max_cc=maxCC,
                                         tier=tier)
        filteredSceneResponse = utils.filter_results_by_pr(sceneResponse, prList)
        print(f'Found {len(filteredSceneResponse)} scenes. Retrieving product ids...')
        legacyIds = [s.get('entityId') for s in filteredSceneResponse]
        dlProductIds = api.get_download_options(dataset_name=datasetName, scene_ids=legacyIds)
        print(f'Writing results to {searchResultsPath}')
        with open(searchResultsPath, 'w') as file:
            json.dump(dlProductIds, file)

    # Consecutive runs: results file exists, check filesystem for existing downloads
    else:
        print(f'Found results from previous search at {searchResultsPath}.\n'
              f'Will check filesystem for existing products.')
        with open(searchResultsPath, 'r') as file:
            dlProductIds = json.load(file)
        assert isinstance(dlProductIds, list) and all(isinstance(element, dict) for element in dlProductIds),\
            f'Results file at {searchResultsPath} seems to be corrupt.\n' \
            f'Did you select the correct file from your last search?'

        # check for scenes already existing in the filesystem
        downloadedScenes = utils.find_downloaded_scenes(search_path=os.path.dirname(searchResultsPath), recursive=True)
        print(f'Found {len(downloadedScenes)} existing products.')
        # only keep products if they don't exist on drive
        tempList = []
        for i in range(len(dlProductIds)):
            if dlProductIds[i]['displayId'] not in downloadedScenes:
                tempList.append(dlProductIds[i])
        dlProductIds = tempList
        print(f'{len(dlProductIds)} products from previous search not found in filesystem.')

    # Generate download links and save to disk
    print(f'Generating download links for {len(dlProductIds)} product bundles.')
    urls = api.get_download_links(dl_product_ids=dlProductIds)

    timeNow = datetime.now().strftime('%Y%m%dT%H%M%S')
    urlsPath = os.path.join(os.path.dirname(searchResultsPath), f'urls_{datasetName}_{timeNow}.txt')

    print(f'Writing download links to {urlsPath}')
    with open(urlsPath, 'w') as file:
        file.write("\n".join(urls))
    print('Done.')
