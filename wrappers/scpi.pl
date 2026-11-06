#!/usr/bin/env perl
use strict;
use warnings;
use IO::Socket::INET;

# Usage: perl wrappers/scpi.pl 127.0.0.1 5025 '*IDN?' 'VOLT 2.5' 'VOLT?'
@ARGV >= 3 or die "usage: scpi.pl HOST PORT COMMAND [COMMAND ...]\n";
my ($host, $port, @commands) = @ARGV;
$SIG{ALRM} = sub { die "SCPI timeout after 2 seconds\n"; };
alarm 2;
my $socket = IO::Socket::INET->new(PeerAddr => $host, PeerPort => $port,
                                  Proto => 'tcp', Timeout => 2)
    or die "connection failed: $!\n";
$socket->autoflush(1);
alarm 0;
my $ok = eval {
    for my $command (@commands) {
        $command !~ /[\r\n]/ && length($command) <= 4095
            or die "command must be one line, at most 4095 characters\n";
        alarm 2;
        print {$socket} "$command\n" or die "write failed: $!\n";
        my $query = $command =~ /\?\s*$/;
        print {$socket} "*OPC?\n" or die "write failed: $!\n" unless $query;
        {
            my $reply = <$socket>;
            defined($reply) or die "server closed before reply\n";
            $reply !~ /^ERROR/ or die $reply;
            print $reply if $query;
        }
        alarm 0;
    }
    1;
};
my $error = $@;
alarm 0;
close $socket;
die $error unless $ok;
