from smartcard.System import readers
from smartcard.util import toHexString, toBytes
from datetime import datetime
from random import randint
from smartcard.Exceptions import CardConnectionException
from smartcard.CardRequest import CardRequest
from smartcard.CardType import AnyCardType


cmd_ADPU = [0x00, 0xA4, 0x04, 0x00]
AID4VISA = [0xA0, 0x00, 0x00, 0x00, 0x03, 0x10, 0x10] # Visa specific AID

def available_readers():
    available_readers = []
    try:
        available_readers = readers()
    except:
        pass
    return available_readers


def card_available():
    reader = available_readers()
    if reader:
        try:
            connection = reader[0].createConnection()
            connection.connect()
            return True, connection
        except CardConnectionException:
            return False, None
        except:
            pass
    return False, None


def get_connection():
    '''
        Select and connect reader device
        return connection state and connection object
    '''
    card_connection = card_available()
    return card_connection[1]



##########################################


def get_PDOL_container_data(cmd_ADPU, AID, connection):
    ''' 
        Sends ADPU command to get the data containing PDOL
        TLV format
    '''

    pdol_container_data, sw1, sw2 = connection.transmit(
        cmd_ADPU + [len(AID)] + AID + [0]
        )
    if not pdol_container_data:
        return 
    pdol_container_data = toHexString(pdol_container_data).replace(" ", "")
    
    return pdol_container_data


def decode_tlv_data(pdol_container_data):
    '''
        6F -> File Control Information
            84 -> Dedicated File
            A5 -> File Control Information
                50 -> Application Label
                87 -> Application Priority Indicator
                9F38 -> PDOL
                BF0C -> File Control Information
                    5F55 -> Issuer Country Code (alpha2 format)
        
        returns a dict:
            {"tag": data}
    ''' 
    tags = {
        "6F": "",
        "84": "",
        "A5": "",
        "50": "",
        "87": "",
        "9F38": "",
        "BF0C": "",
        "5F55": ""
    }

    data = pdol_container_data 
    
    for k, v in tags.items():

        if data.find(k) == -1:
            continue

        if len(k) == 2:
            DF_length = int(data[data.find(k)+2:data.find(k)+4], 16) # hex to dec
            DF = data[data.find(k)+4:data.find(k)+4+DF_length*2] # *2 because there is no space between hex values
        elif len(k) == 4:
            DF_length = int(data[data.find(k)+4:data.find(k)+6], 16) 
            DF = data[data.find(k)+6:data.find(k)+6+DF_length*2] 
    
        tags[k] = DF

    return tags


def format_hex(number):
    return "{:02x}".format(number)


def generate_PDOL_response(PDOL):
    ''' We create the PDOL response
        based on the PDOL specifications
    '''
    
    ## This code is based on one of the exercises in the book 
    ## <<Show me the (e-) money Hacking a sistemas de pagos digitales: 
    ##  NFC. RFID, MST y Chips EMV>> author Salvador Mendoza.

    PDOL_default = "80A80000"
    none_PDOL = "80A8000002830000" # If PDOL is ""

    if PDOL != "":

        PDOL_byte_list = toBytes(PDOL) # [159, 102, 4, 159, 2, 6, 159, 55, 4, 95, 42, 2]
        data = ""
        counter = len(PDOL_byte_list)
        index = 0

        while (index < counter): 

            if (PDOL_byte_list[index] == 0x9F and PDOL_byte_list[index+1] == 0x66 and PDOL_byte_list[index+2] == 0x04): 
                data += "F620C000"
                index += 3            
            elif (PDOL_byte_list[index] == 0x95):
                cl = PDOL_byte_list[index+1]
                while cl > 0:
                    data += "AA"
                    cl -= 1
                index += 2
            elif (PDOL_byte_list[index] == 0x9F and PDOL_byte_list[index+1] == 0x1A and PDOL_byte_list[index+2] == 0x02):
                data += "0250"
                index +=3
            elif (PDOL_byte_list[index] == 0x5F and PDOL_byte_list[index+1] == 0x2A and PDOL_byte_list[index+2] == 0x02):
                data += "0840"
                index += 3
            elif (PDOL_byte_list[index] == 0x9A):
                dt = datetime.now()
                data += dt.strftime("%y%m%d")
                index += 2
            elif (PDOL_byte_list[index] == 0x9F and PDOL_byte_list[index+1] == 0x37 and PDOL_byte_list[index+2] == 0x04):
                unpredictable_number = "{:08x}".format(randint(0, 0xFFFFFFFF))
                data += unpredictable_number
                index += 3
            elif (PDOL_byte_list[index] == 0x9C):
                data += "00"
                index += 2
            elif (PDOL_byte_list[index] == 0x9F and PDOL_byte_list[index+2] == 0x01):
                cl = PDOL_byte_list[index+2]
                while cl > 0:
                    data += "00"
                    cl -= 1
                index += 3
            else: # Para combinaciones menores a 3 bytes
                cl = PDOL_byte_list[index+2]
                while cl > 0: 
                    data += "00"
                    cl -= 1 
                index += 3

        generated_PDOL_response = PDOL_default + format_hex(len(data)//2+2) + "83" + format_hex(len(data)//2) + data + "00"
        return generated_PDOL_response
    else:
        return none_PDOL
        
        

def get_track_2(generated_PDOL_response, connection):

    track2 = ""
    
    track2_response, sw1, sw2 = connection.transmit(toBytes(generated_PDOL_response))
    track2_response = toHexString(track2_response).replace(" ", "")
    # Tag <57> corresponds to Track 2
    track2_i = track2_response.find("57") # Start index
    
    if track2_i > 0:
        track2_i += 4
        track2_j = track2_i + (int(track2_response[track2_i-2:track2_i], 16) * 2) # End index
        track2 = track2_response[track2_i:track2_j]
    
    return track2
        


def get_VISA_info():
    '''
        Calls all the methods we need to
        VISA card type info
            and
        returns tags dictionary and track2 string 
    '''
    connection = get_connection()

    if connection is not None:
    
        pdol_container_data = get_PDOL_container_data(cmd_ADPU, AID4VISA, connection)
        tags_dict = decode_tlv_data(pdol_container_data)
        pdol = tags_dict["9F38"]
        generated_PDOL_response = generate_PDOL_response(pdol) 
        track2 = get_track_2(generated_PDOL_response, connection)
        
        decoded_track2_dict = decode_track2(track2)
        tags_dict = rename_tags_dict_keys(tags_dict)
        visa_info = {**tags_dict, **decoded_track2_dict} # Merge

        return visa_info

    return 


        
def decode_track2(track2):
    '''
        According to ISO/IEC 7813, excluding start sentinel, end sentinel, 
        and Longitudinal Redundancy Check (LRC), as follows: 
        Primary Account Number (n, var. up to 19) Field Separator (Hex 'D')
        (b) Expiration Date (YYMM) (n 4) Service Code (n 3) Discretionary Data 
        (defined by individual payment systems) (n, var.) Pad with one Hex 'F' 
        if needed to ensure whole bytes (b)
    '''
    d = track2.find("D")
    pan = track2[:d]
    ed = track2[d+1:d+1+4] # YYMM
    ed = ed[2:] + "/" + ed[:2] # MM/YY
    sc = track2[d+5:d+5+3]
    dd = track2[d+5+3:track2.find("F")]

    return {
            "Primary Account Number (PAN)": pan, 
            "Expiration Date": ed,
            "Service Code": sc,
            "Discretionary Data": dd
            }

def rename_tags_dict_keys(tags_dict):
    '''
        We replace the tags as the dictionary key to 
        add its full name and make it easier to read from the interface
        
        <<AND>>

        decode Application Label and Issuer Country Code tags.
        File Control Information tags have long values,
        that's why we split them.
    '''

    tags_dict = {
        "[6F] - File Control Information": tags_dict["6F"],
        "[84] - Dedicated File": tags_dict["84"],
        "[A5] - File Control Information": tags_dict["A5"],
        "[50] - Application Label": bytearray.fromhex(tags_dict["50"]).decode(),
        "[87] - Application Priority Indicator": tags_dict["87"],
        "[9F38] - Processing Options Data Object List (PDOL)": tags_dict["9F38"],
        "[BF0C] - File Control Information": tags_dict["BF0C"],
        "[5F55] - Issuer Country Code": bytearray.fromhex(tags_dict["5F55"]).decode()
    }

    #Splitting
    for k, v in tags_dict.items():
        if "File Control Information" in k:
            tags_dict[k] = v[:len(v)//2] + "\n" + v[:len(v)//2+1]
             
    return tags_dict
