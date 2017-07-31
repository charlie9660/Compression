#!/opt/alttools/bin/python
import struct
    
read_buffer = 0
read_count = 0
order = 4

#character Symbol
class Symbol():
    def __init__(self, symbol):
        self.symbol = symbol
        self.range = 1


#collection of symbols
class dict():
    def __init__(self, predictor=''):
        self.predictor = predictor
        self.symbols = []
        self.total = 0
        self.shorterPredictorbundle = None
        
# A 30-bit arithmetic decoder   
class Decoder():

    value_max = 1 << 30 - 1
  
    def __init__(self, coded_file):
        self.lowbound = 0
        self.upbound = 0xffffffff
        self.underflowbound = 0
        self.coded_file = coded_file
        self.start_position = coded_file.tell()
        self.value = 0
        
        i = 0
        #proceed to read 4 bytes of data
        while(i<32):
            self.value = (self.value << 1) | read_bit(coded_file)  
            i = i + 1      

    def decode(self, bundle_lowbound, bundle_upbound, bundle_total):

        if bundle_total == None:
            return self.value, self.upbound - self.lowbound + 1
            
        range = self.upbound - self.lowbound + 1
        
        #compute the scaled upbound and lowbound
        self.upbound = self.lowbound + (range * bundle_upbound + bundle_total - 1) / bundle_total - 1
        self.lowbound = self.lowbound + (range * bundle_lowbound + bundle_total - 1) / bundle_total
        
        while (1==1):
            #check if the most significant bits are equal
            if (self.lowbound ^ self.upbound) & 0x80000000 == 0:
                pass
                
            #process data if upbound has 1 in most significant bit and lowbound has 1 in second msb         
            elif (self.lowbound & 0xc0000000) == 0x40000000 and (self.upbound & 0xc0000000) == 0x80000000:
                self.value = self.value ^ 0x40000000
                self.lowbound = self.lowbound & 0x3fffffff
                self.upbound = self.upbound | 0x40000000
            
            else:
                break

            # shift for the next bit and keep 32 bitformat
            self.lowbound = (self.lowbound << 1) & 0xffffffff
            self.upbound = ((self.upbound << 1) | 0x01) & 0xffffffff
            bit = read_bit(self.coded_file)
            self.value = ((self.value << 1) | bit) & 0xffffffff

        return self.value - self.lowbound, self.upbound - self.lowbound + 1
                
                
#PPMC decoder
class DictDecode():
    def __init__(self, clear_file, coded_file, decoder):
    
        self.decoder = decoder
        self.decoder_value, self.decoder_range = decoder.decode(None, None, None)

        self.predictor = ''   #matching character sequence
        self.bundle = None
        self.bundles = {}
        self.bundles[self.predictor] = dict()

    #method to return the symbol
    def get(self):
       

        # find the bundle with the longest predictor
        predictor = self.predictor
         
        #if sequence not found, reduce the length of sequence by 1
        while predictor not in self.bundles:
            predictor = predictor[1:]

        bundle = self.bundles[predictor]
        exclusions = []


        while bundle != None:
        
            #calculate the number of escape characters
            apr_esc_len = max(len(bundle.symbols), 1)
            
            #total number of characters indicate position
            total = bundle.total + apr_esc_len
            if exclusions:
                
                #exclude the symbols in exclusions
                for c in bundle.symbols:
                    if c.symbol in exclusions:
                        total = total - c.range

                # sometimes bundles have all symbols excluded.
                if total == apr_esc_len:
                    bundle = bundle.shorterPredictorbundle
                    continue

            # find decoder_value in bundle
            found = None
            symbol = None
            escape = None
            code = self.decoder_value * (total) // self.decoder_range
            if code < total - apr_esc_len:
                lowbound = 0
                for c in bundle.symbols:
                    if c.symbol not in exclusions:
                        upbound = lowbound + c.range
                        if lowbound + c.range > code >= lowbound:
                            found = c
                            symbol = c.symbol

                            self.decoder_value, self.decoder_range = \
                                self.decoder.decode(lowbound, upbound, total)
                
                            bundle = None
                            break

                        lowbound = upbound
     
            if not found:
                lowbound = total - apr_esc_len
                range = apr_esc_len
                upbound = lowbound + range
                self.decoder_value, self.decoder_range = \
                    self.decoder.decode(lowbound, upbound, total)
              
                for s in bundle.symbols:
                    exclusions.append(s.symbol)
                bundle = bundle.shorterPredictorbundle
                
        # generate escape symbol if not found
        if not found:
            symbol = self.put()
            escape = symbol

        # update current bounds 
        self.update(symbol, lowbound, upbound, escape)

        #make sure the matching sequence is not longer than the order number (4)
        if order > 0:
            if len(self.predictor) >= order:
                self.predictor = self.predictor[1:len(self.predictor)] + chr(symbol)
            else:
                self.predictor = self.predictor + chr(symbol)

        return symbol


    def update(self, value, lowbound, upbound, escape):
        # find the bundle with the longest predictor sequence
        # create all those missing
        predictor = self.predictor
        new_bundle = None
        while predictor not in self.bundles:
            bundle = self.bundles[predictor] = dict(predictor)
            if new_bundle:
                new_bundle.shorterPredictorbundle = bundle
            new_bundle = bundle
            predictor = predictor[1:]

        if new_bundle:
            new_bundle.shorterPredictorbundle = self.bundles[predictor]
        bundle = self.bundles[self.predictor]


        # update bundles
        symbol = value if escape == None else escape
        while bundle != None:
            found = None
            for s in bundle.symbols:
                if s.symbol == symbol:
                    s.range = s.range + 1
                    found = s
                    break
            if found == None:
                s = Symbol(symbol)
                bundle.symbols.append(s)

            bundle.total = bundle.total + 1
            self.renew_counts(bundle)

            bundle = bundle.shorterPredictorbundle

    #
    def put(self):
        symbol = (self.decoder_value * 256) // self.decoder_range

        self.decoder_value, self.decoder_range = \
            self.decoder.decode(symbol, symbol + 1, 256)
        return symbol
    
    #renew make sure that all the values are sorted. convert to list from dictionary and then
    #the sort is performed. Context range cut to half
    def renew_counts(self, bundle):
        if bundle.total + 1 >= self.decoder.value_max:
            total = 0
            for c in bundle.symbols:
                range = c.range // 2
                if range < 1:
                    range = 1
                c.range = range
                total = total + range

            bundle.symbols.sort(key=lambda i: i.symbol)
            bundle.symbols.sort(key=lambda i: i.range, reverse=True)

            bundle.total = total



#read a bit from the file, form a byte to fill the read buffer
def read_bit(in_file):
   
    global read_buffer
    global read_count
    
    if read_count == 0:
        v = in_file.read(1)
        if len(v) > 0:
            read_buffer = struct.unpack("<B", v)[0]
        else:
            read_buffer = 0
        read_count = 8

    bit = (read_buffer >> (read_count - 1)) & 1
    read_count = read_count - 1
            
    return bit
    
    
#main function
def decode_file(out_name, in_name):

        in_file = open(in_name, "rb")
        
        #skip the header(which contains the description prj1.txt and and testing code for deubgging)
        in_file.seek(15,0)
        size = struct.unpack("<L", in_file.read(4))[0]
        out_file = open(out_name, "wb")
        in_file.seek(20,0)
        
        decoder = Decoder(in_file)
        bundle = DictDecode(out_file, in_file, decoder)
        
        while size >0:
        	symbol = bundle.get()
        	size = size -1
        	#print(symbol)
        	out_file.write(struct.pack("B", symbol))
        	#print(str(struct.pack("B", symbol)))
        
        in_file.close()
        out_file.close()
   
    

decode_file("out.txt","compressed.cd") 