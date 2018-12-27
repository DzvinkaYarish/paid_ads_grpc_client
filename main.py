# -*- coding: utf-8 -*-
import rpc_pb2 as ln
import rpc_pb2_grpc as lnrpc
import grpc
import os
import codecs
import sys
import time

try:
    assert (len(sys.argv) == 4)
except AssertionError:
    print('Please, specify amount, receiver(site/advert) and whether to close channel after payment')
    exit()

amount = int(sys.argv[1])
receiver = sys.argv[2]
close_channel = sys.argv[3]

with open(os.path.expanduser('~/bob_lnd_node/data/chain/bitcoin/simnet/admin.macaroon'), 'rb') as f:
    macaroon_bytes_b = f.read()
    macaroon_b = codecs.encode(macaroon_bytes_b, 'hex')

with open(os.path.expanduser('~/charlie_lnd_node/data/chain/bitcoin/simnet/admin.macaroon'), 'rb') as f:
    macaroon_bytes_c = f.read()
    macaroon_c = codecs.encode(macaroon_bytes_c, 'hex')


def metadata_callback_b(context, callback):
    # for more info see grpc docs
    callback([('macaroon', macaroon_b)], None)

def metadata_callback_c(context, callback):
    # for more info see grpc docs
    callback([('macaroon', macaroon_c)], None)


os.environ["GRPC_SSL_CIPHER_SUITES"] = 'HIGH+ECDSA'

pubkey_charlie = '025a5f0d9cdf970c8b65ec4a5869a5eb315d9a99aeca07e55139478350e5639ac7'
b_pubkey_charlie = b'025a5f0d9cdf970c8b65ec4a5869a5eb315d9a99aeca07e55139478350e5639ac7'
host_bob = '3'


pubkey_bob = '034ab0341fffb446ce5b4f28b142eb0557cfdeeb5cdcdc62f0a712b164f768fca5'
b_pubkey_bob = b'034ab0341fffb446ce5b4f28b142eb0557cfdeeb5cdcdc62f0a712b164f768fca5'
host_charlie = '4'

cert = open(os.path.expanduser('~/.lnd/tls.cert'), 'rb').read()

cert_creds = grpc.ssl_channel_credentials(cert)

auth_creds_bob = grpc.metadata_call_credentials(metadata_callback_b)

auth_creds_charlie = grpc.metadata_call_credentials(metadata_callback_c)


# combine the cert credentials and the macaroon auth credentials
# such that every call is properly encrypted and authenticated
combined_creds_bob = grpc.composite_channel_credentials(cert_creds, auth_creds_bob)

combined_creds_charlie = grpc.composite_channel_credentials(cert_creds, auth_creds_charlie)


channel_bob = grpc.secure_channel('localhost:1000{}'.format(host_bob), combined_creds_bob)
stub_bob = lnrpc.LightningStub(channel_bob)

channel_charlie = grpc.secure_channel('localhost:1000{}'.format(host_charlie), combined_creds_charlie)
stub_charlie = lnrpc.LightningStub(channel_charlie)


# print(stub_bob.GetInfo(ln.GetInfoRequest()))
# print(stub_bob.GetInfo(ln.GetInfoRequest()))


r = stub_bob.ListPeers(ln.ListPeersRequest())
if pubkey_charlie not in [peer.pub_key for peer in r.peers]:
    req_connect_peer = ln.ConnectPeerRequest(addr=ln.LightningAddress(pubkey=pubkey_charlie, host='localhost:1001{}'.format(host_charlie)))
    r = stub_bob.ConnectPeer(req_connect_peer)
    print(r)

r = stub_bob.ListChannels(ln.ListChannelsRequest())
if pubkey_charlie not in [ch.remote_pubkey for ch in r.channels]:
    req_open_channel = ln.OpenChannelRequest(
            node_pubkey=b_pubkey_charlie,
            node_pubkey_string=u'{}'.format(codecs.decode(pubkey_charlie, 'hex')),
            local_funding_amount=20000,
            push_sat=5000
            )


    r = stub_bob.OpenChannel(req_open_channel)
    print(r)

req_add_invoice = ln.Invoice(value=amount)
if receiver == 'site':
    r = stub_bob.AddInvoice(req_add_invoice)
else:
    r = stub_charlie.AddInvoice(req_add_invoice)

payment_request = r.payment_request


def request_generator():
    while True:
        req_send_payment = ln.SendRequest(
            payment_request=payment_request,
            amt=amount
        )

        yield req_send_payment


request_iterable = request_generator()
if receiver == 'site':
    for response in stub_charlie.SendPayment(request_iterable):
            if response.payment_error == 'unable to find a path to destination':
                print('Not enough funds to make a payment')
                break
else:
    for response in stub_bob.SendPayment(request_iterable):
        if response.payment_error == 'unable to find a path to destination':
            print('Not enough funds to make a payment')
            break


time.sleep(15)

if close_channel == 'true':
    r = stub_bob.ListChannels(ln.ListChannelsRequest())

    print(r)

    if r.channels:
        ch_point = ln.ChannelPoint(funding_txid_bytes=bytes(r.channels[0].channel_point.split(':')[0], 'utf-8'),
                                   funding_txid_str=u'{}'.format(r.channels[0].channel_point.split(':')[0]),
                                   output_index=int(r.channels[0].channel_point.split(':')[1])
                                   )
        r = stub_bob.CloseChannel(ln.CloseChannelRequest(channel_point=ch_point))
        for i in r:
            print(i)



print(stub_bob.WalletBalance(ln.WalletBalanceRequest()))
print(stub_charlie.WalletBalance(ln.WalletBalanceRequest()))




