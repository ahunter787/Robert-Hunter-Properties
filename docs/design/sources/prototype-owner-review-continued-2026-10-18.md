# Austin Notes Continued

Preserved verbatim from the Interactive Prototype document before consolidation.
Source: http://10.60.0.227:8090/doc/operations-desk-interactive-prototype-VHoelpO6PQ
The original attachment URLs are retained; the screenshots have not been replaced.

![Notice the Alignment Issue With "Back to Results"](/api/attachments.redirect?id=90c8c353-7de4-4371-8802-8a54682ae166 " =2486x792")

Just like clicking on a tenant box opens that tenant page, I want to have each property box be clickable, and that causes it to expand. Right now, there is only a small button to expand “Alder court” But intuitively, clicking on the box that is Alder Court should expand it. \n\n ![Here is another one. See alder court is expanded? When I clicked on "Cedar house Property Overview" Alder court collapsed. So I opened it again to see it, but I'm on All Properties / Cedar house. I want manual control over expanding and collapsing properties. They should remain aware of their state when I move into a different one. So if I had Alder Court open on Property Preview, when I click on Cedar House Apartment 1, Alder Court should remain expanded. ](/api/attachments.redirect?id=c656aad1-faa1-4c53-b4d3-aa94669fb197 " =792x937")

 ![Properties (A)](/api/attachments.redirect?id=ba501de2-2d01-4572-b398-59a49dafd176 " =2605x1673") ![All Properties (B)](/api/attachments.redirect?id=ee19b939-4bd4-416e-9d12-3a44af886926 " =2605x1673")

These two workflows are clashing with each other. We need to consolidate them into a single workflow, and figure out if any information is unique on one of the pages. \n\nThe caption names are my reference names for the screenshot: A and B\nImagine Clicking Properties in the navbar brings you to the All Properties (B) page. That tiny 2nd navbar is turned into the ui of “Properties screenshot”. Then the actual dashboard changes into what we see in “All Properties” if a unit is selected. If a Property is selected, we see property overview page. Then we don’t have a specific property overview portion in the 2nd navbar section. 

 ![This is the idea... Where clicking on Alder Court will take it to the property overview. Clicking on Studio A on the middle nav bar will open to the current screen. ](/api/attachments.redirect?id=7bb8fa4e-5902-42b1-995a-e6d64b023975 " =2605x1673")

Check for any menus or paths that become destroyed with this workflow, we’ll need to repair.
