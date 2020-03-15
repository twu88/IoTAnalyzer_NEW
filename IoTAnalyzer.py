#************************************** Import area *************************************************
import timeit
import xlrd
import requests
from scapy.all import *

def loadfile(filename):
    '''loads a pcap file and returns a object containing the pcap'''
    start = timeit.default_timer()
    print("start loading")
    packets = rdpcap(filename)
    stop = timeit.default_timer()
    print("loading finished after: ", stop - start)
    return packets

def lookupIP(ip):
    '''returns json file with location data'''
    url = 'http://api.ipstack.com/' + ip + '?access_key=75ae5d89ba88b940232c4e8f26d6f7e8'.format(ip)
    res = requests.get(url)
    return res.json()

def fillDictWithLocation(ipList):
    '''takes an existing list of ips and looksup the ips and fills a dictionary with the ips and their location information'''
    storrage= {}
    for ip in ipList:
        if ((ip != '255.255.255.255') and not (re.search('^192.168.', ip)) and not (ip != '0.0.0.0')):  #checks if the data goes to the broadcasting address or stays in the local network
            jsonCashed = lookupIP(ip)
            storrage[ip] = {'country': jsonCashed['country_name'],
                            'region_name': jsonCashed['region_name'],
                            'longitude': jsonCashed['longitude'],
                            'latitude': jsonCashed['latitude'],
                            'continent': jsonCashed['continent_code'],
                            'city': jsonCashed['city']}
        else:
            storrage[ip] = {'location': "local IP address"}
    return storrage

def buildLocationSet(locationSet, ip_dictionary):
    '''creates a set with all ips within a given dictionary returns a set with ip adresses'''
    for k, v in ip_dictionary.items():
        if((k != "secure packages") and (k != "unsecure packages")):                                                    #to prevent that this two keys dont get parsed
            locationSet.add(k)
            for k1, v1 in v.items():
                for k2, v2 in v1.items():
                    if ((k2 != "secure packages") and (k2 != "unsecure packages")):                                     #to prevent that this two keys dont get parsed
                        locationSet.add(k2)
    return locationSet

def buildDictWithBothIp(storrage, oriIp, destiIp):
    '''creates a dictionary based on origin ips and a dictionary with their destinations'''
    if(oriIp in storrage.keys()):
        if(destiIp in storrage[oriIp]["targetIp"].keys()):
            storrage[oriIp]["targetIp"][destiIp] +=1
        else:
            storrage[oriIp]["targetIp"][destiIp] = 1
    else:
        storrage[oriIp] = {"targetIp": {destiIp: 1}}
    return storrage

def printLocationJson(jsonData):
    '''takes json input and prints location'''
    ip_address = jsonData['ip']
    continent = jsonData['continent_code']
    latitude = jsonData['latitude']
    longitude = jsonData['longitude']
    capital = jsonData['city']

    print('Latitude : {}'.format(latitude))
    print('Longitude : {}'.format(longitude))
    print('IP adress : {}'.format(ip_address))
    print('Continent : {}'.format(continent))
    print('City : {}'.format(capital))

def getProtocolName(number):
    '''looksup the name of the protocol based on its number'''
    table = {num: name[8:] for name, num in vars(socket).items() if name.startswith("IPPROTO")}
    return table[number]

def createPortDict(incDict, package):
    '''creates a dictionary with all ports'''
    outgoingDict = incDict
    #print(package.show())
    if(package.getlayer("TCP").sport in outgoingDict.keys()):
        outgoingDict[package.getlayer("TCP").sport] +=1
    else:
        outgoingDict[package.getlayer("TCP").sport] = 1

    if(package.getlayer("TCP").dport in outgoingDict.keys()):
        outgoingDict[package.getlayer("TCP").dport] +=1
    else:
        outgoingDict[package.getlayer("TCP").dport] = 1

    return outgoingDict

def initializePortWhitelist():
    '''reades an external excel file which contains the port whitelist and returns an array with all whitelisted ports'''
    portWhiteList = list()
    loc = ("portWhiteList.xlsx")
    wb = xlrd.open_workbook(loc)
    sheet = wb.sheet_by_index(0)
    sheet.cell_value(0, 0)
    for i in range(sheet.nrows):
        portWhiteList.append(int(sheet.cell_value(i, 0)))
    return portWhiteList

def checkPortSecurity(port, portWhiteList):
    '''checks if port is in the whitelist'''
    if(port in portWhiteList):
        return True
    return False

def addPorts(dictionary, package, portWhiteList, oriIp):
    '''adds if the connection was secure or unsecure to the ip dictionary'''
    if((package.getlayer("TCP").sport in portWhiteList) or (package.getlayer("TCP").dport in portWhiteList)):
        if("secure packages" in dictionary[oriIp]["targetIp"].keys()):
            dictionary[oriIp]["targetIp"]["secure packages"] +=1
        else:
            dictionary[oriIp]["targetIp"]["secure packages"] = 1
    else:
        if ("unsecure packages" in dictionary[oriIp]["targetIp"].keys()):
            dictionary[oriIp]["targetIp"]["unsecure packages"] +=1
        else:
            dictionary[oriIp]["targetIp"]["unsecure packages"] = 1
    return dictionary

def createCleartextDictionary(packets):
    ''' clearTextFinder tackets a list of packages
    the function will then write the cleartext if, it was byte enconded, into a dictionary which will be returned afterwards '''
    clearTextDictionary = {}
    for packet in packets:
            if (packet.getlayer("Raw")):
                try:
                    result = packet.getlayer('Raw').load.decode().strip()
                    #result = re.sub(r'[\W+|_]', '', result)                                                            # \W+ deletes all special characters, \d+ deletes all numbers, |_ deletes all underscores
                    destIp = packet.getlayer("IP").dst                                                                  # retrieves the destination ip of the packet from the IP layer
                    oriIp = packet.getlayer("IP").src                                                                   # retrieves the ip from the packet is sent
                    if (oriIp in clearTextDictionary.keys()):
                        if (destIp in clearTextDictionary[oriIp]["targetIp"].keys()):
                            clearTextDictionary[oriIp]["targetIp"][destIp] += ("; "+result)
                        else:
                            clearTextDictionary[oriIp]["targetIp"][destIp] = result
                    else:
                        clearTextDictionary[oriIp] = {"targetIp": {destIp: result}}
                except:
                    pass
                finally:
                    pass
            else:
                print(packet.summary())
    return clearTextDictionary

def entropy(data):
    e = 0
    counter = collections.Counter(data)
    #print("counter ", counter)
    l = len(data)
    for count in counter.values():
        # count is always > 0
        p_x = count / l
        e += - p_x * math.log2(p_x)
    return e

def prepareEntropyDic(dict, entropy, oriIp, destIp):
    if (oriIp in dict.keys()):
        if (destIp in dict[oriIp].keys()):
            dict[oriIp][destIp]["amount"] += 1
            dict[oriIp][destIp]["averageEntropy"] += entropy  # calculates the averrage entropy between the two IPs
        else:
            dict[oriIp][destIp] = {"averageEntropy": entropy, "amount": 1}
    else:
        dict[oriIp] = {destIp: {"averageEntropy": entropy, "amount": 1}}
    return dict

def finishEntropyDic(dict):
    print(dict)
    for o in dict:
        for d in (dict[o].keys()):
            dict[o][d]["averageEntropy"] /= dict[o][d]["amount"]                                                        # calculates the averrage entropy between the two IPs
    return dict


def stepZeroEntropy(packets, upperLimit = 9, lowerLimit = 0):
    sessions = packets.sessions()
    amountRaw = 0
    amountdone = 0
    amountdonesemi = 0
    amountdoneExcluded = 0
    amount = 0
    entropyDic = {}

    """for session in sessions:
        for packet in sessions[session]:"""
    for packet in packets:
            amount += 1
            if (packet.getlayer("Raw")):
                destIp = packet.getlayer("IP").dst  # retrieves the destination ip of the packet from the IP layer
                oriIp = packet.getlayer("IP").src  # retrieves the ip from the packet is sent
                if (entropy(packet.getlayer('Raw').load) > lowerLimit and entropy(packet.getlayer('Raw').load) < upperLimit):
                    try:
                        impText = packet.getlayer('Raw').load.decode().strip()
                        payload = re.sub(r'[\W+|_]', '',impText)                                                        # \W+ deletes all special characters, \d+ deletes all numbers, |_ deletes all underscores
                        ent = entropy(payload)                                                                          #entropy UTF-8 based without special character
                        # print(entropy(packet.getlayer('Raw').load))                                                #entropy based on rawdata
                        amountdone += 1
                        entropyDic = prepareEntropyDic(entropyDic, ent, oriIp, destIp)
                    except:
                        try:
                            amountdonesemi += 1
                            payload = packet.getlayer('Raw').load
                            ent = entropy(payload)
                            # print(e)
                            entropyDic = prepareEntropyDic(entropyDic, ent, oriIp, destIp)
                        except:
                            print("something went wrong")
                            print("NEXT FILE")
                        # print(packet.getlayer('Raw').load.decode())
                        # print(packet.lastlayer().load)
                else:
                    amountdoneExcluded += 1
                    pass
            else:
                amountRaw += 1
                pass

    finishEntropyDic(entropyDic)
    print("amount packets total", amount)
    print("amount no Raw level", amountRaw)
    print("amount done byte based", amountdonesemi)
    print("amount done utf8 based", amountdone)
    print("amount done utf8 based but to high or low", amountdoneExcluded)
    print("total: ", amountdone + amountdonesemi + amountRaw + amountdoneExcluded)
    return entropyDic



def stepZeroDictBuildBothIps(packets, portWhiteList):
    '''takes the the packets and the portWhiteList to create the IP dicitonary and the port dictionary'''
    print("start building dictionary")
    dictionary = {}
    portDictionary = {}
    #protocolList = set()

    """ for p in packets:
        if (p.getlayer("TCP")):
            if(p.getlayer("TCP").chksum == 0x343b):
                print(p.getlayer("TCP").show())
                print(p.getlayer("TCP").chksum)
                """

    for p in packets:
        if (p.getlayer("IP")):  # checks if the packet uses the IP layer
            # if ((p.getlayer("IP").dst != '255.255.255.255') and not (re.search('^192.168.', p.getlayer("IP").dst))):  #checks if the data goes to the broadcasting
                                                                                                                        # address or stays in the local network
            destIp = p.getlayer("IP").dst  # retrieves the destination ip of the packet from the IP layer
            oriIp = p.getlayer("IP").src  # retrieves the ip from the packet is sent
            dictionary = buildDictWithBothIp(dictionary, oriIp, destIp)

            if (p.getlayer("TCP")):  # checks if the packet uses the TCP layer
                dictionary = addPorts(dictionary,p, portWhiteList, oriIp)
                portDictionary = createPortDict(portDictionary, p)
            #protocolList.add(p.getlayer("IP").proto)

    print("finished building the dictionary")
    """    print(protocolList)
    for t in protocolList:
        print(getProtocolName(t))"""

    sortedPortDictionary = {}
    for i in sorted(portDictionary):                                    #sorts the dictionary based on the keys
        sortedPortDictionary.update({i : portDictionary[i]})
    return (dictionary, sortedPortDictionary)

def startTimer ():
    '''starts an initial timer'''
    print("program start")
    return timeit.default_timer()

def end(start):
    '''ends the initial timer and prints elapsed time'''

    stop = timeit.default_timer()
    print("program finished after: ", stop - start)

def main():
    start = startTimer()                                                #creates a timestamp for the startingtime
    # filename = input("Please enter the name of the pcap file: ")      #to enter the filename during runtime
    filename = 'withings_monitor_merge.pcap'
    #filename = 'camera.pcap'
    packets = loadfile(filename)                                        #holds the data of pcap file
    locationSet = set()                                                 #creates an empty set to increase readability, this set will contain all IPs

    portWhiteList = initializePortWhitelist()                           #holds a list with all "safe" ports
    ipDictionary, sortedPortDictionary = stepZeroDictBuildBothIps(packets, portWhiteList) #returns a dictionaries with IPs and their destination IPs to which they communicate and a dictionary with all used ports and their amount used
    locationSet = buildLocationSet(locationSet,ipDictionary)            #holds a list with all IPs (destinations an origins)
    locationDictionary = fillDictWithLocation(locationSet)              #holds a dictionaries with all IPs and their geolocation informations
    cleartextDictionary = createCleartextDictionary(packets)            #holds a dictionary with all with all IP who sent cleartext with the corresponding destination address and the cleartext
    entropyDictionary = stepZeroEntropy(packets)

    print("Overview of all used Ports and call amounts: ", sortedPortDictionary)
    print("Overview of origin and destination IPs: ", ipDictionary)
    print("Overview of IPs and their geolocation: ", locationDictionary)
    print("Overview of IPs their send cleartext and the destination IP: ", cleartextDictionary)
    print("Overview of IPs their destination and the average entropy: ", entropyDictionary)
    end(start)

if __name__ == "__main__":
    main()