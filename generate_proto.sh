python -m grpc_tools.protoc \
  -I./src/proto \
  --python_out=./src/proto \
  --grpc_python_out=./src/proto \
  src/proto/customer.proto \
  src/proto/product.proto

sed -i '' 's/import customer_pb2/from src.proto import customer_pb2/g' src/proto/customer_pb2_grpc.py
sed -i '' 's/import product_pb2/from src.proto import product_pb2/g' src/proto/product_pb2_grpc.py

echo "Proto stubs regenerated and imports fixed."