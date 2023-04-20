#@String inDir
#@String outDir

run("Grid/Collection stitching", 
	   "type=[Positions from file] " + 
	   "order=[Defined by TileConfiguration] " +
	   "directory=" + inDir + " " + 
	   "output_textfile_name=TileConfiguration.txt " + 
	   "fusion_method=[Linear Blending] " + 
	   "regression_threshold=0.30 " +
	   "max/avg_displacement_threshold=2.50 " + 
	   "absolute_displacement_threshold=3.50 " + 
	   "frame=1 " + 
	   "subpixel_accuracy " + 
	   "display_fusion " + 
	   "computation_parameters=[Save computation time (but use more RAM)] " +
	   "image_output=[Fuse and display] ");
	   
run("Make Composite");
saveAs("PNG", outDir + "/output.png");
close("*");
