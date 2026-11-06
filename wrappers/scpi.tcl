#!/usr/bin/env tclsh
# Compatible with Tcl 8.5 as shipped with macOS. Usage: HOST PORT COMMAND ...
if {$argc < 3} {
    puts stderr "usage: scpi.tcl HOST PORT COMMAND ?COMMAND ...?"
    exit 2
}
proc ready {channel} {
    set ::reply [gets $channel]
    if {[fblocked $channel]} {return}
    if {[eof $channel]} {
        set ::failure "server closed before a complete newline-terminated reply"
    }
    set ::done 1
}
proc waitFor {channel mode} {
    set ::done 0
    set ::failure ""
    if {$mode eq "writable"} {
        fileevent $channel writable {set ::done 1}
    } else {
        fileevent $channel readable [list ready $channel]
    }
    set timer [after 2000 {set ::failure "SCPI timeout after 2 seconds"; set ::done 1}]
    vwait ::done
    after cancel $timer
    fileevent $channel $mode {}
    if {$::failure ne ""} {error $::failure}
}
set channel ""
set failed [catch {
    set channel [socket -async [lindex $argv 0] [lindex $argv 1]]
    fconfigure $channel -blocking 0 -buffering line -translation lf -encoding ascii
    waitFor $channel writable
    set connectionError [fconfigure $channel -error]
    if {$connectionError ne ""} {error $connectionError}
    foreach command [lrange $argv 2 end] {
        if {[regexp {[\r\n]} $command] || [string length $command] > 4095} {
            error "command must be one line, at most 4095 characters"
        }
        puts $channel $command
        flush $channel
        set query [regexp {\?\s*$} $command]
        if {!$query} {puts $channel "*OPC?"; flush $channel}
        waitFor $channel readable
        if {[string match "ERROR*" $::reply]} {error $::reply}
        if {!$query && $::reply ne "1"} {error "operation did not complete"}
        if {$query} {puts $::reply}
    }
} message]
if {$channel ne ""} {catch {close $channel}}
if {$failed} {puts stderr $message; exit 1}
