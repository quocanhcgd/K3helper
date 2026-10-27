# CFS Slot Mapping on K3

Creality Print v7.3.0 treats CFS slot choice as a mapping between the sliced job's logical filaments and physical CFS slots. The mapping is job metadata; the reviewed source does not show Creality Print inserting the selected physical slot directly into the uploaded G-code.

## What Creality Print sends

The source builds a `color_match_info` array with fields including `extruderId`, `boxId`, `boxType`, `materialId`, filament type, colors, and a slot label. The mapping service builds this array from the selected material slots in [FilamentMappingService.cpp](https://github.com/CrealityOfficial/CrealityPrint/blob/v7.3.0/src/slic3r/GUI/simple/filamentMapping/FilamentMappingService.cpp). The send workflow carries it alongside the uploaded file and print request in [SendToPrinter.cpp](https://github.com/CrealityOfficial/CrealityPrint/blob/v7.3.0/src/slic3r/GUI/print_manage/App/SendToPrinter.cpp) and [EasyPrintSender.cpp](https://github.com/CrealityOfficial/CrealityPrint/blob/v7.3.0/src/slic3r/GUI/simple/sendWorkflow/EasyPrintSender.cpp).

For LAN printing, Creality Print dispatches a vendor-specific `send_print_cmd`. Its source does not demonstrate that Moonraker accepts `color_match_info` through `printer.print.start` or another standard Moonraker method. The cloud route also has a separate Creality payload, as shown in [CxCloudPrintExecutor.cpp](https://github.com/CrealityOfficial/CrealityPrint/blob/v7.3.0/src/slic3r/GUI/simple/sendWorkflow/CxCloudPrintExecutor.cpp).

## Current K3 Helper behavior

The Fluidd CFS panel reads Klipper's `box` object and displays the reported slot state. It does not select a slot or alter print jobs. Creality Print's metadata format alone is not enough to implement this safely: the K3 firmware's supported Moonraker-side mapping interface and the relationship between a logical G-code tool (`T0`, `T1`, and so on) and the CFS slot must first be verified.

Do not treat `BOX_LOAD_MATERIAL` or a low-level feed command as equivalent to print mapping. Loading filament into the extruder does not establish how later tool changes in a multi-material G-code file will be routed. A Fluidd implementation must map each job filament to a physical slot and pass that mapping through a K3-supported print-start path, then verify the result on the printer.

Until that protocol is verified, CFS status remains informational and Fluidd print/reprint behavior is unchanged. Spoolman tracks spool inventory and usage; it does not select the physical CFS slot.
