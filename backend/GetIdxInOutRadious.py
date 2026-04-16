import numpy as np

def compute_distance(latlong1, latlong2):
    """
    Compute the distance between a latlong value and a vector of latlong values.
    
    Arguments:
    latlong1 -- Tuple representing the latlong value.
    latlong2 -- List of tuples representing the latlong values of the vector.
    
    Returns:
    List of distances between the latlong value and each point in the vector.
    """
    lat1, lon1 = latlong1 #This is unpacking the tuple breaking out the latitude value into lat1 and the longitude value into lon1
    lat2, lon2 = np.array(latlong2).T #This is separating an array of values and allowing the lat2, lon2 to take on the appropriate values from the array
    
    # Convert degrees to radians
    lat1_rad = np.radians(lat1)
    lon1_rad = np.radians(lon1)
    lat2_rad = np.radians(lat2)
    lon2_rad = np.radians(lon2)
    
    # Haversine formula
    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad
    a = np.sin(delta_lat/2)**2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(delta_lon/2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
    
    # Radius of the Earth in kilometers
    r = 6371
    
    # Calculate the distance
    distances = r * c
    
    return distances

#latlong1: Transmission
#latlong2: Devices
#latlong1 is a vector of points and latlong2 is a vector of points
def GetIdxOutRadious(latlong1, latlong2, Radious):
    IdxOut=[]
    #if latlong2=[], return IdxOut=[]
    try:
        for i in range(latlong1.shape[0]): #The shape will be i rows and j columns - likely just 2 columns (a latitutde and a longitude value). This looks at the [0] position of the shape which would be the number of rows. Effectively this makes sure we iterate
            #through each pair of lat/long coordinates in the array of latlong1
            D=compute_distance(latlong1[i,:], latlong2) #Here it is computing the distance of the ith row (a specific lat/long combination point in latlong1) against another lat/long point in latlong2. 
            IdxOut.append(np.where(D>=Radious)[0])
        return IdxOut
    except:
        if len(latlong2)==0:
            IdxOut=[[]]*latlong1.shape[0]
            return IdxOut
        else:
            return print("Error in GetIdxOutRadious function")


#Which turbines are inside the radious of the tranmission system
#latlong1 is a vector of points and latlong2 is a vector of points
def GetIdxInRadious(latlong1, latlong2, Radious):
    IdxOut=[]
    
    try:
        for i in range(latlong1.shape[0]):
            D=compute_distance(latlong1[i,:], latlong2)
            IdxOut.append(np.where(D<=Radious)[0])
        return IdxOut
    except:
        if len(latlong2)==0:
            IdxOut=[[]]*latlong1.shape[0]
            return IdxOut
        else:
            return print("Error in GetIdxInRadious function")


#In this case we determine the index of the devices that are inside the radious of the transmission system
#Considering latlong1 as a single point and latlong2 as a vector of points
def GetIdxInRadious_Simple(latlong1, latlong2, Radious):
    IdxIn=[]
    D=compute_distance(latlong1, latlong2)
    return np.where(D<=Radious)[0]